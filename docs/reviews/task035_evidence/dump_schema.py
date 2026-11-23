"""Task 035C：从 PostgreSQL 测试库导出实际 schema（只读）。

用法（仓库根目录）：

    D:/anacada/envs/commercial-agent/python.exe -X utf8 docs/reviews/task035_evidence/dump_schema.py

约定：

- 连接串只从环境变量 ``COMMERCIAL_PG_TEST_URL`` 读取，不接受参数；
- 脚本只执行 SELECT / 系统目录查询，不建表、不迁移、不写入；
- 输出里不出现连接串、用户名或密码，只有表、列、约束与服务端版本。

导出的约束来自两处：SQLAlchemy ``inspect``（主键 / 唯一 / CHECK / 外键）与
``pg_constraint`` 目录查询（``EXCLUDE USING gist`` 不在 ``inspect`` 的
CHECK 列表里，单独列出）。
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect, text

URL_ENV = "COMMERCIAL_PG_TEST_URL"
ALEMBIC_TABLE = "alembic_version"


def _dump_table(inspector, dialect, table: str) -> None:
    print(f"\n== 表 {table} ==")

    print("-- 列")
    for column in inspector.get_columns(table, schema="public"):
        compiled = column["type"].compile(dialect=dialect)
        nullable = "NOT NULL" if not column["nullable"] else "NULL"
        default = column.get("default")
        default_sql = f" default={default}" if default not in (None, "") else ""
        print(f"   {column['name']:<28} {str(compiled):<26} {nullable}{default_sql}")

    primary_key = inspector.get_pk_constraint(table, schema="public")
    print(f"-- 主键: {primary_key.get('name') or '(未命名)'} {primary_key.get('constrained_columns')}")

    unique_constraints = inspector.get_unique_constraints(table, schema="public")
    if unique_constraints:
        print("-- 唯一约束")
        for item in unique_constraints:
            print(f"   {item.get('name')}: {item.get('column_names')}")

    check_constraints = inspector.get_check_constraints(table, schema="public")
    if check_constraints:
        print("-- CHECK 约束")
        for item in check_constraints:
            print(f"   {item.get('name')}: {item.get('sqltext')}")

    foreign_keys = inspector.get_foreign_keys(table, schema="public")
    if foreign_keys:
        print("-- 外键")
        for item in foreign_keys:
            print(
                f"   {item.get('name')}: {item.get('constrained_columns')} -> "
                f"{item.get('referred_table')}{item.get('referred_columns')}"
            )


def _dump_exclusion_constraints(connection) -> None:
    rows = connection.execute(
        text(
            "SELECT t.relname, c.conname, pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE c.contype = 'x' AND n.nspname = 'public' "
            "ORDER BY t.relname, c.conname"
        )
    ).all()
    print("\n== PostgreSQL 排他约束（EXCLUDE）==")
    if not rows:
        print("   (none)")
    for table, name, definition in rows:
        print(f"   {table}.{name}: {definition}")


def main() -> int:
    url = os.environ.get(URL_ENV, "").strip()
    if not url:
        print(f"未设置 {URL_ENV}，无法导出 schema", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar_one()
            revision = connection.execute(
                text(f"SELECT version_num FROM {ALEMBIC_TABLE}")
            ).scalar_one_or_none()
            tables = sorted(
                name
                for name in inspect(connection).get_table_names(schema="public")
                if name != ALEMBIC_TABLE
            )

            print("-- 数据来源：环境变量 COMMERCIAL_PG_TEST_URL 指向的 PostgreSQL 测试库")
            print("-- （连接串、用户名、密码均不输出）")
            print(f"-- server version: {version}")
            print(f"-- alembic_version: {revision}")
            print(f"-- 业务表数量: {len(tables)}：{', '.join(tables)}")

            inspector = inspect(connection)
            for table in tables:
                _dump_table(inspector, engine.dialect, table)

            _dump_exclusion_constraints(connection)

            check_count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
                )
            ).scalar_one()
            exclusion_count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE contype = 'x' AND connamespace = 'public'::regnamespace"
                )
            ).scalar_one()
            print("\n== 汇总 ==")
            print(f"   业务表: {len(tables)}")
            print(f"   CHECK 约束: {check_count}")
            print(f"   EXCLUDE 约束: {exclusion_count}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
