"""数据库会话与只读闸门（Task 010）。

业务工具只允许读取。只读不仅靠"代码里没写 UPDATE"，还在连接层强制：

- SQLite：`PRAGMA query_only = ON`
- PostgreSQL：`SET TRANSACTION READ ONLY`

这样即使未来有人误加写操作，也会在数据库侧失败，而不是悄悄改数据。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session


def create_engine_for(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {"future": True, "echo": echo}
    if url.startswith("sqlite"):
        # 允许在内存/临时文件中被多个连接共享
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@contextmanager
def session_scope(engine: Engine, *, read_only: bool = True) -> Iterator[Session]:
    with Session(engine) as session:
        if read_only:
            _enforce_read_only(session)
        yield session


def _enforce_read_only(session: Session) -> None:
    bind = session.get_bind()
    name = bind.dialect.name
    if name == "sqlite":
        session.execute(text("PRAGMA query_only = ON"))
    elif name == "postgresql":
        session.execute(text("SET TRANSACTION READ ONLY"))


def sqlite_url(path: str | Path) -> str:
    return f"sqlite+pysqlite:///{Path(path).as_posix()}"