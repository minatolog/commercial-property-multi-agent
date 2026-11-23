"""本地/测试数据库装配（Task 010 / 016）。

本机没有 PostgreSQL 服务，因此离线验证使用 SQLite：

- 模型定义、查询逻辑、Decimal 转换、只读闸门都可验证；
- PostgreSQL 专属能力（原生 `NUMERIC`、`EXCLUDE` 排他约束、RLS）**无法在本机验证**，
  这一限制在任务 010 归档中明确记录，不做"已验证"表述。

Task 016（S2）：装配仓库用的 Session 现在**真正开启只读闸门**。
之前直接用 `Session(engine)`，`PRAGMA query_only` 从未生效，
"连接层强制只读"只是文档里的承诺。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ..paths import DEFAULT_FIXTURE_PATH, SQLITE_DB_PATH
from .repository import DatabaseRepository
from .seed import create_schema, seed_from_fixture
from .session import create_engine_for, enforce_read_only

__all__ = [
    "build_postgres_repository",
    "build_readonly_repository_for_engine",
    "build_repository_for_engine",
    "build_sqlite_repository",
]


def _readonly_repository(engine: Engine, fixture_path: str | Path | None) -> DatabaseRepository:
    """装配只读仓库（不建表、不 seed）。"""

    path = Path(fixture_path or DEFAULT_FIXTURE_PATH)
    data = json.loads(path.read_text(encoding="utf-8"))
    repository_session = Session(engine)
    # 只读闸门必须在**装配期**启用：工具仓库拿到的就是这个 Session
    enforce_read_only(repository_session)
    repository = DatabaseRepository(
        repository_session,
        dataset_version=data["dataset_version"],
        as_of_date=date.fromisoformat(data["as_of_date"]),
    )
    for principal in data.get("principals", {}).values():
        repository.register_principal(principal)
    return repository


def build_repository_for_engine(
    engine: Engine,
    fixture_path: str | Path | None = None,
    *,
    create_tables: bool = True,
) -> DatabaseRepository:
    """在给定 engine 上（可选建表）导入 fixture 并返回只读仓库。

    PostgreSQL 实机测试先用迁移建表，再传 `create_tables=False` 复用这里的
    seed + 只读装配，避免测试另写一份装配逻辑。
    """

    path = Path(fixture_path or DEFAULT_FIXTURE_PATH)
    if create_tables:
        create_schema(engine)
    setup = Session(engine)
    try:
        seed_from_fixture(setup, path)
        setup.commit()
    finally:
        setup.close()
    return _readonly_repository(engine, path)


def build_readonly_repository_for_engine(
    engine: Engine, fixture_path: str | Path | None = None
) -> DatabaseRepository:
    """连接**已迁移、已有数据**的库并装配只读仓库（不建表、不 seed）。

    数据集元数据（`dataset_version` / `as_of_date` / 可信主体）来自 fixture 文件，
    与数据库内容的一致性由迁移 / seed 步骤保证；业务工具本身只读数据库。
    """

    return _readonly_repository(engine, fixture_path)


def build_postgres_repository(
    url: str, fixture_path: str | Path | None = None
) -> tuple[Engine, DatabaseRepository]:
    """按 URL 构建只读 PostgreSQL 仓库（供 CLI 的 `--backend postgresql` 使用）。

    - engine 必须由 `create_engine_for` 创建：数据集时区写在连接启动参数里
      （Task 035A），直接 `create_engine` 读出的时间仍是 UTC；
    - 不建表、不 seed：CLI 只连接已经迁移并导入数据的库。
    """

    if not url.startswith("postgresql"):
        raise ValueError("PostgreSQL 只读仓库需要 postgresql:// 连接串")
    engine = create_engine_for(url)
    try:
        repository = build_readonly_repository_for_engine(engine, fixture_path)
    except Exception:
        engine.dispose()
        raise
    return engine, repository


def build_sqlite_repository(
    fixture_path: str | Path | None = None, *, in_memory: bool = True
) -> tuple[Engine, DatabaseRepository]:
    path = Path(fixture_path or DEFAULT_FIXTURE_PATH)

    if in_memory:
        engine = create_engine(
            "sqlite+pysqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:  # pragma: no cover - 仅用于人工检查
        from .session import create_engine_for, sqlite_url

        # 落到仓库内的 data/business/（已被 .gitignore 排除），避免在 cwd 生成游离文件
        SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine_for(sqlite_url(SQLITE_DB_PATH))

    repository = build_repository_for_engine(engine, path)
    return engine, repository