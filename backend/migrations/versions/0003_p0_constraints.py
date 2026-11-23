"""add P0 CHECK / EXCLUDE constraints

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23

Task 035B：为已实现的 12 张业务表补 P0 约束。

取值依据（fixture `docs/evaluation/fixtures/agent_first_v1.json` + 现有代码 +
`docs/architecture/database_design.md` 的状态机/约束章节）：

- fixture 中实际出现的值：租约 `active`；账单 `issued`；收款 `confirmed` / `reversed`；
  收款方式 `bank_transfer` / `cheque`；工单 `closed` / `in_progress`，类别
  `hvac` / `electrical`，优先级 `normal` / `high`；文档 `lease_contract` / `attachment`，
  `document_status=signed`；计费规则 `rent` / `property_fee`、`per_sqm`、`month`。
- 枚举覆盖设计文档 §9 状态机与 §6 各表定义的全部合法值（例如租约 `draft` /
  `pending_signature` / `terminated` / `cancelled`），避免约束拒绝正常业务流转。
- fixture 没有负数调整行，但设计 §6.9 明确“仅调整类明细允许负数（减免/冲抵）”，
  因此 `invoice_items.amount` 使用 `charge_type = 'other_fee' OR amount >= 0`，
  而不是无条件的 `>= 0`；其余金额按 fixture 实际值设下限（押金 `>= 0`、收款与
  核销 `> 0`、面积 `> 0`）。

SQLite 说明：

- 金额/面积/数量在 SQLite 上以 TEXT 存储（见 `models.Money` / `UnitPrice`），
  直接与数字比较会按文本比较（`'0.00' > 0` 为真），所以 SQLite 分支统一用
  `CAST(col AS REAL)`，保证零值/正负判断正确；PG 上保持 `NUMERIC` 原生比较。
- 币种：PG 用正则 `~ '^[A-Z]{3}$'`；SQLite 没有默认 REGEXP 实现，改用
  `length(currency) = 3 AND currency = upper(currency)`。
- `EXCLUDE USING gist`（租期不冲突）是 PostgreSQL 专属能力，SQLite 上跳过；
  SQLite 上**不保证**租期不重叠（本任务不补触发器/生成列，也没有应用层校验）。

运行权限：PG 分支会 `CREATE EXTENSION IF NOT EXISTS btree_gist`。执行迁移的
数据库账号需要具备 `CREATE EXTENSION` 权限，或由 DBA 预先安装该扩展。
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

#: (表, 约束名, PG 条件, SQLite 条件)
#: SQLite 条件为 None 时沿用 PG 条件（仅用于两种方言语义相同的表达式）。
_CHECKS: tuple[tuple[str, str, str, str | None], ...] = (
    # ---- projects ----
    ("projects", "ck_projects_status_p0",
     "status IN ('active', 'inactive', 'archived')", None),
    # ---- units ----
    ("units", "ck_units_area_positive_p0", "area_sqm > 0", "CAST(area_sqm AS REAL) > 0"),
    ("units", "ck_units_chargeable_area_positive_p0",
     "chargeable_area_sqm > 0", "CAST(chargeable_area_sqm AS REAL) > 0"),
    ("units", "ck_units_physical_status_p0",
     "physical_status IN ('normal', 'maintenance', 'closed')", None),
    # ---- tenants ----
    ("tenants", "ck_tenants_status_p0",
     "status IN ('active', 'inactive', 'blacklisted')", None),
    # ---- leases ----
    ("leases", "ck_leases_status_p0",
     "status IN ('draft', 'pending_signature', 'active', 'terminated', 'cancelled')", None),
    ("leases", "ck_leases_billing_cycle_p0",
     "billing_cycle IN ('monthly', 'quarterly', 'semi_annual', 'annual')", None),
    ("leases", "ck_leases_date_range_p0", "end_date >= start_date", None),
    ("leases", "ck_leases_payment_terms_days_p0",
     "payment_terms_days BETWEEN 0 AND 180", None),
    ("leases", "ck_leases_deposit_non_negative_p0",
     "deposit_amount >= 0", "CAST(deposit_amount AS REAL) >= 0"),
    ("leases", "ck_leases_currency_format_p0",
     "currency ~ '^[A-Z]{3}$'", "length(currency) = 3 AND currency = upper(currency)"),
    # ---- lease_charge_rules ----
    ("lease_charge_rules", "ck_charge_rules_charge_type_p0",
     "charge_type IN ('rent', 'property_fee', 'utility', 'other_fee')", None),
    ("lease_charge_rules", "ck_charge_rules_calculation_method_p0",
     "calculation_method IN ('fixed_amount', 'per_sqm')", None),
    ("lease_charge_rules", "ck_charge_rules_period_unit_p0",
     "period_unit IN ('day', 'month', 'quarter', 'year')", None),
    ("lease_charge_rules", "ck_charge_rules_amount_non_negative_p0",
     "amount IS NULL OR amount >= 0", "amount IS NULL OR CAST(amount AS REAL) >= 0"),
    ("lease_charge_rules", "ck_charge_rules_unit_price_non_negative_p0",
     "unit_price IS NULL OR unit_price >= 0",
     "unit_price IS NULL OR CAST(unit_price AS REAL) >= 0"),
    ("lease_charge_rules", "ck_charge_rules_effective_range_p0",
     "effective_to >= effective_from", None),
    ("lease_charge_rules", "ck_charge_rules_calc_consistency_p0",
     "(calculation_method = 'fixed_amount' AND amount IS NOT NULL AND unit_price IS NULL) "
     "OR (calculation_method = 'per_sqm' AND unit_price IS NOT NULL AND amount IS NULL)",
     None),
    # ---- invoices ----
    ("invoices", "ck_invoices_period_range_p0", "period_end >= period_start", None),
    ("invoices", "ck_invoices_due_after_issue_p0", "due_date >= issue_date", None),
    ("invoices", "ck_invoices_status_p0", "status IN ('draft', 'issued', 'void')", None),
    ("invoices", "ck_invoices_currency_format_p0",
     "currency ~ '^[A-Z]{3}$'", "length(currency) = 3 AND currency = upper(currency)"),
    # ---- invoice_items ----
    ("invoice_items", "ck_invoice_items_charge_type_p0",
     "charge_type IN ('rent', 'property_fee', 'utility', 'other_fee')", None),
    ("invoice_items", "ck_invoice_items_amount_adjustment_p0",
     "charge_type = 'other_fee' OR amount >= 0",
     "charge_type = 'other_fee' OR CAST(amount AS REAL) >= 0"),
    ("invoice_items", "ck_invoice_items_quantity_nonzero_p0",
     "quantity <> 0", "CAST(quantity AS REAL) <> 0"),
    ("invoice_items", "ck_invoice_items_unit_price_non_negative_p0",
     "unit_price IS NULL OR unit_price >= 0",
     "unit_price IS NULL OR CAST(unit_price AS REAL) >= 0"),
    # ---- payments ----
    ("payments", "ck_payments_amount_positive_p0",
     "amount > 0", "CAST(amount AS REAL) > 0"),
    ("payments", "ck_payments_status_p0",
     "status IN ('pending_confirmation', 'confirmed', 'reversed')", None),
    ("payments", "ck_payments_method_p0",
     "payment_method IN ('bank_transfer', 'cash', 'cheque', 'online', 'other')", None),
    ("payments", "ck_payments_currency_format_p0",
     "currency ~ '^[A-Z]{3}$'", "length(currency) = 3 AND currency = upper(currency)"),
    # ---- payment_allocations ----
    ("payment_allocations", "ck_payment_allocations_amount_positive_p0",
     "amount > 0", "CAST(amount AS REAL) > 0"),
    # ---- work_orders ----
    ("work_orders", "ck_work_orders_category_p0",
     "category IN ('hvac', 'electrical', 'plumbing', 'structure', 'cleaning', "
     "'security', 'other')", None),
    ("work_orders", "ck_work_orders_priority_p0",
     "priority IN ('low', 'normal', 'high', 'urgent')", None),
    ("work_orders", "ck_work_orders_status_p0",
     "status IN ('open', 'assigned', 'in_progress', 'on_hold', 'resolved', "
     "'closed', 'cancelled')", None),
    ("work_orders", "ck_work_orders_resolved_after_reported_p0",
     "resolved_at IS NULL OR resolved_at >= reported_at", None),
    ("work_orders", "ck_work_orders_resolved_status_time_p0",
     "status NOT IN ('resolved', 'closed') OR resolved_at IS NOT NULL", None),
    # ---- documents ----
    ("documents", "ck_documents_doc_type_p0",
     "doc_type IN ('lease_contract', 'attachment', 'inspection_report', "
     "'invoice_scan', 'work_order_photo', 'other')", None),
    ("documents", "ck_documents_version_positive_p0", "version > 0", None),
    ("documents", "ck_documents_status_p0",
     "document_status IN ('signed', 'draft', 'draft_unsigned')", None),
)

#: PostgreSQL 专属：同一商铺的生效租约（status='active'）期间不得重叠。
EXCLUSION_CONSTRAINT = "ex_leases_unit_active_period_p0"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _is_sqlite():
        # SQLite 不支持 ALTER TABLE ADD CONSTRAINT；batch 模式会重建表。
        tables: dict[str, list[tuple[str, str]]] = {}
        for table, name, condition, sqlite_condition in _CHECKS:
            tables.setdefault(table, []).append((name, sqlite_condition or condition))
        for table, checks in tables.items():
            with op.batch_alter_table(table, recreate="always") as batch:
                for name, condition in checks:
                    batch.create_check_constraint(name, condition)
        return

    for table, name, condition, _sqlite_condition in _CHECKS:
        op.create_check_constraint(name, table, condition)

    # 租期不冲突（PG 专属）。`btree_gist` 提供 text 的 GiST 等值操作符；
    # 区间用闭区间 `[]`，与 fixture / 仓库查询的“含首尾日”语义一致。
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        f"ALTER TABLE leases ADD CONSTRAINT {EXCLUSION_CONSTRAINT} "
        "EXCLUDE USING gist ("
        "unit_id WITH =, "
        "daterange(start_date, end_date, '[]') WITH &&"
        ") WHERE (status = 'active')"
    )


def downgrade() -> None:
    if _is_sqlite():
        tables: dict[str, list[str]] = {}
        for table, name, _condition, _sqlite_condition in _CHECKS:
            tables.setdefault(table, []).append(name)
        for table, names in tables.items():
            with op.batch_alter_table(table, recreate="always") as batch:
                for name in names:
                    batch.drop_constraint(name, type_="check")
        return

    op.execute(f"ALTER TABLE leases DROP CONSTRAINT IF EXISTS {EXCLUSION_CONSTRAINT}")
    # 不删除 btree_gist：扩展可能是其它对象（或运维人员）安装/共用的。
    for table, name, _condition, _sqlite_condition in _CHECKS:
        op.drop_constraint(name, table, type_="check")
