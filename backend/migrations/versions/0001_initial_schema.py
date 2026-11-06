"""initial schema from ORM metadata

Revision ID: 0001
Revises:
Create Date: 2026-11-06

说明：初始迁移直接由 `Base.metadata` 建表，避免手写 13 张表的重复定义产生漂移。
**后续任何变更必须使用显式 `op.` 操作**；并且 PostgreSQL 专属约束
（`EXCLUDE USING gist`、部分唯一索引）需要 `op.execute(...)` 手写，
Alembic autogenerate 不会生成它们（见 docs/architecture/database_design.md 2.5）。
"""

from __future__ import annotations

from alembic import op

from app.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())