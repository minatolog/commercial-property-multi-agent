"""Alembic 环境：从环境变量读取数据库 URL。"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DEFAULT_URL = "sqlite+pysqlite:///./commercial_agent_migrate.db"
# 环境变量优先；其次保留调用方（测试/程序）设置的值；最后才落回默认值。
_override = os.environ.get("COMMERCIAL_DB_URL")
if _override:
    config.set_main_option("sqlalchemy.url", _override)
elif not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", DEFAULT_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()