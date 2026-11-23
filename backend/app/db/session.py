"""数据库会话与只读闸门（Task 010 / 035A）。

业务工具只允许读取。只读不仅靠"代码里没写 UPDATE"，还在连接层强制：

- SQLite：`PRAGMA query_only = ON`
- PostgreSQL：每个事务开头都执行 `SET TRANSACTION READ ONLY`

这样即使未来有人误加写操作，也会在数据库侧失败，而不是悄悄改数据。

Task 035A（PostgreSQL 实机）：

- 只读不再只覆盖第一个事务——`SET TRANSACTION READ ONLY` 随事务结束失效，
  `rollback()` / `commit()` 之后的新事务会恢复可写。现在在 Session 的
  `after_begin` 上为**每个**新事务重新声明只读；
- PG 连接统一设置数据集时区（`DATASET_TIMEZONE`），使 `timestamptz`
  读出的 ISO 字符串与 fixture 的 `+08:00` 完全一致。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session

__all__ = [
    "DATASET_TIMEZONE",
    "create_engine_for",
    "enforce_read_only",
    "session_scope",
    "sqlite_url",
]

#: 数据集时区。fixture 中的时间字段均为 `+08:00`，PG 连接（seed 与只读）
#: 都按这个时区呈现，避免同一时刻以 UTC 展示造成 8 小时偏差。
DATASET_TIMEZONE = "Asia/Shanghai"


def create_engine_for(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {"future": True, "echo": echo}
    if url.startswith("sqlite"):
        # 允许在内存/临时文件中被多个连接共享
        kwargs["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql"):
        # 时区通过连接启动参数设置，而不是 connect 事件里的 `SET TIME ZONE`：
        # 连接归还连接池时会重置换状态（实测复用连接恢复成 Etc/UTC），只有启动
        # 参数在每次建立连接时生效，seed 连接与只读连接因此始终是数据集时区。
        kwargs["connect_args"] = {"options": f"-c timezone={DATASET_TIMEZONE}"}
    return create_engine(url, **kwargs)


@contextmanager
def session_scope(engine: Engine, *, read_only: bool = True) -> Iterator[Session]:
    with Session(engine) as session:
        if read_only:
            _enforce_read_only(session)
        yield session


def enforce_read_only(session: Session) -> None:
    """在给定 Session 上启用只读闸门（SQLite: PRAGMA，PostgreSQL: READ ONLY 事务）。

    公开此函数是为了让装配层显式调用——"只读"必须是**实现**，而不是文档承诺。
    """

    _enforce_read_only(session)


def _postgres_transaction_read_only(_session, transaction, connection) -> None:
    # SAVEPOINT 不是新事务，不需要（也不能）重新声明 READ ONLY。
    if getattr(transaction, "nested", False):
        return
    # 直接在当前 Connection 上执行：此时事务已开始、尚未运行任何语句。
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")


def _enable_postgres_read_only(session: Session) -> None:
    """让 PG 只读覆盖会话的整个生命周期，而不只是第一个事务。

    选择 `after_begin` + 每事务 `SET TRANSACTION READ ONLY`，而不是连接级的
    `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`：

    - 只读会话 `rollback()` / `commit()` 后会开启新事务，事务级声明随之失效；
      `after_begin` 保证每个新事务都重新声明，写入始终被拒；
    - `SET SESSION CHARACTERISTICS` 属于连接级设置，连接归还连接池后仍保留，
      可能把后续复用的写连接（如 seed 装配）也变成只读，故障方向不可控。
    """

    if not session.info.get("postgres_read_only_gate"):
        event.listen(session, "after_begin", _postgres_transaction_read_only)
        session.info["postgres_read_only_gate"] = True
    # 触发 autobegin，让第一个事务也经 after_begin 声明为只读。
    session.execute(text("SELECT 1"))


def _enforce_read_only(session: Session) -> None:
    bind = session.get_bind()
    name = bind.dialect.name
    if name == "sqlite":
        session.execute(text("PRAGMA query_only = ON"))
    elif name == "postgresql":
        _enable_postgres_read_only(session)


def sqlite_url(path: str | Path) -> str:
    return f"sqlite+pysqlite:///{Path(path).as_posix()}"