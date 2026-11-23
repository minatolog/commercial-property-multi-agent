"""PostgreSQL 只读数据库角色（Task 035B）。

会话级 `SET TRANSACTION READ ONLY` 只是“误写保护”，不是权限边界：连接用的
建表账号可以随时 `SET TRANSACTION READ WRITE`。真正的边界是**只有 SELECT
权限的数据库角色**。

本模块是运维 / 测试用函数，不在业务路径里自动调用：

- `create_readonly_role`：创建可登录角色，只授予业务表的 `SELECT`，并用
  `ALTER DEFAULT PRIVILEGES` 覆盖之后新建的表；不给任何写权限，也不给
  `alembic_version`（迁移版本表不是业务数据）。
- `drop_readonly_role`：回收授权并删除角色。

安全：

- 角色名只允许 `[a-z_][a-z0-9_]*`（且不超过 PostgreSQL 的 63 字节标识符上限），
  标识符再经 SQLAlchemy 方言转义，杜绝拼接注入；
- 密码先由服务器 `quote_literal()` 转义再拼入 DDL（PostgreSQL 的实用语句不接受
  绑定参数），密码本身不出现在日志/异常消息里；
- 仅支持 PostgreSQL；SQLite 直接报错，避免“以为建了角色、实际没建”。
"""

from __future__ import annotations

import re
import secrets

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .models import Base

__all__ = ["RoleCreationError", "create_readonly_role", "drop_readonly_role"]

_ROLE_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
_MAX_IDENTIFIER_BYTES = 63


class RoleCreationError(RuntimeError):
    """创建只读角色失败。

    数据库拒绝 `CREATE ROLE` 时，SQLAlchemy 的原始异常会把整条语句
    （含明文密码）放进消息。调用方看到的这个异常**消息不含 SQL/密码**，
    且以 `raise ... from None` 抛出，traceback 不再展示原始异常。
    """


def _password_literal(password: str) -> str:
    """把密码包成 PostgreSQL dollar-quoted 字符串常量。

    不使用 `quote_literal()` 的绑定参数，也不把密码当作 `text()` 的参数：
    密码只出现在最终 `CREATE ROLE` 语句里；执行走 `exec_driver_sql`，
    由此避开 SQLAlchemy 对 `:name` 的绑定参数解析。

    psycopg 3（即使不传参数）仍会扫描整条 SQL 的 `%` 占位符，明文 `%` 必须写成
    `%%`，由驱动还原为单个 `%`。dollar-quote 标签随机生成并确认不在密码中出现，
    其余字符（引号、反斜杠、冒号）无需转义。
    """

    for _ in range(8):
        tag = f"$ro_{secrets.token_hex(6)}$"
        if tag not in password:
            return f"{tag}{password}{tag}".replace("%", "%%")
    raise ValueError("无法为密码选择安全的转义标签（请更换密码）")


def _require_postgres(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise ValueError(
            f"只读角色只能在 PostgreSQL 上创建（当前方言: {engine.dialect.name}）"
        )


def _validate_role_name(role_name: str) -> None:
    if not isinstance(role_name, str) or not _ROLE_NAME_PATTERN.fullmatch(role_name):
        raise ValueError(
            "角色名只允许 [a-z_][a-z0-9_]*（小写字母/数字/下划线，且不能以数字开头）"
        )
    if len(role_name.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"角色名超过 PostgreSQL 标识符上限 {_MAX_IDENTIFIER_BYTES} 字节")


def _quote(engine: Engine, identifier: str) -> str:
    return engine.dialect.identifier_preparer.quote(identifier)


def _business_tables() -> tuple[str, ...]:
    """已实现的业务表（不含 `alembic_version`）。"""

    return tuple(table.name for table in Base.metadata.sorted_tables)


def _role_exists(connection, role_name: str) -> bool:
    return (
        connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": role_name}
        ).scalar()
        is not None
    )


def create_readonly_role(engine: Engine, role_name: str, password: str) -> None:
    """创建只读登录角色，仅授予业务表的 SELECT（含未来新表）。"""

    _require_postgres(engine)
    _validate_role_name(role_name)
    if not isinstance(password, str) or not password:
        raise ValueError("只读角色必须有非空密码")

    role = _quote(engine, role_name)
    with engine.begin() as connection:
        if _role_exists(connection, role_name):
            raise ValueError(f"角色已存在: {role_name!r}")
        statement = (
            f"CREATE ROLE {role} LOGIN PASSWORD {_password_literal(password)} "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        try:
            # exec_driver_sql：不做 text() 的 `:name` 参数解析，也不给 psycopg
            # 传参数（因此密码中的 `%` 不会被当作占位符）。
            connection.exec_driver_sql(statement)
        except SQLAlchemyError:
            # 原异常的 [SQL: ...] / [parameters: ...] 会带明文密码；替换掉，
            # 并且不保留异常链。
            raise RoleCreationError(
                f"创建只读角色失败（角色名 {role_name!r}）；"
                "为避免泄露密码，错误详情不包含 SQL 文本，请查看数据库日志"
            ) from None

        database = connection.execute(text("SELECT current_database()")).scalar_one()
        connection.execute(
            text(f"GRANT CONNECT ON DATABASE {_quote(engine, str(database))} TO {role}")
        )
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        for table in _business_tables():
            connection.execute(text(f"GRANT SELECT ON {_quote(engine, table)} TO {role}"))
        # 将来由同一账号新建的表也自动只读（不包含改表前的 alembic_version）。
        connection.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT SELECT ON TABLES TO {role}"
            )
        )


def drop_readonly_role(engine: Engine, role_name: str) -> None:
    """回收只读角色的授权并删除角色（角色不存在时静默返回）。"""

    _require_postgres(engine)
    _validate_role_name(role_name)

    role = _quote(engine, role_name)
    with engine.begin() as connection:
        if not _role_exists(connection, role_name):
            return
        connection.execute(
            text(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {role}")
        )
        connection.execute(
            text(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {role}")
        )
        connection.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"REVOKE SELECT ON TABLES FROM {role}"
            )
        )
        connection.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {role}"))
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        connection.execute(
            text(f"REVOKE CONNECT ON DATABASE {_quote(engine, str(database))} FROM {role}")
        )
        connection.execute(text(f"DROP ROLE IF EXISTS {role}"))
