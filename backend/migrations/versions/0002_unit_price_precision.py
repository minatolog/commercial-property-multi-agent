"""widen unit price / quantity to NUMERIC(14,4)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23

Task 035A：单价（`lease_charge_rules.unit_price`、`invoice_items.unit_price`）
与数量（`invoice_items.quantity`）此前复用 2 位小数的 `Money`，fixture 中的
`132.3000` 会被静默截成 `132.30`。这里用**显式 `op.alter_column`** 扩到 4 位，
金额字段（`amount` 等）保持 `NUMERIC(14,2)`。

SQLite 上这两类是 TEXT，4 位精度由 `UnitPrice` 在 Python 侧 quantize 保证，
列类型无需改动，因此本迁移在 SQLite 上不做 DDL（`upgrade`/`downgrade` 均可执行）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

#: (表, 列)：需要 4 位小数的列。
_UNIT_PRICE_COLUMNS = (
    ("lease_charge_rules", "unit_price"),
    ("invoice_items", "unit_price"),
    ("invoice_items", "quantity"),
)


def _alter_columns(from_type: sa.Numeric, to_type: sa.Numeric) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite：TEXT 存储，精度由 UnitPrice 保证，不需要改列类型。
        return
    for table, column in _UNIT_PRICE_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=from_type,
            type_=to_type,
        )


def upgrade() -> None:
    _alter_columns(sa.Numeric(14, 2), sa.Numeric(14, 4))


def downgrade() -> None:
    _alter_columns(sa.Numeric(14, 4), sa.Numeric(14, 2))
