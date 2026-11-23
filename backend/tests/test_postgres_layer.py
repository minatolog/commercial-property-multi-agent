"""Task 035A：PostgreSQL 实机测试（迁移、seed、等价性、只读闸门、端到端）。

只在设置了 `COMMERCIAL_PG_TEST_URL` 时运行；未设置时整个模块跳过，
默认 SQLite 回归不依赖 PostgreSQL。连接串只从环境变量读取，不写入仓库。

每个测试类自己 `downgrade base` → `upgrade head` → seed，
不依赖执行顺序，结束时清库。
"""

from __future__ import annotations

import os
import unittest
from decimal import Decimal

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.agents.base.contracts import AgentContext
from app.agents.base.errors import AgentError, ErrorCode
from app.agents.factory import build_registry
from app.db.bootstrap import build_repository_for_engine
from app.db.models import InvoiceItem, LeaseChargeRule
from app.db.session import (
    DATASET_TIMEZONE,
    create_engine_for,
    session_scope,
)
from app.fixtures.repository import FixtureRepository
from app.paths import BACKEND_ROOT
from app.runtime.budget import Budget
from app.runtime.types import TraceLog

PG_URL = os.environ.get("COMMERCIAL_PG_TEST_URL")
PG_SKIP_REASON = (
    "未设置 COMMERCIAL_PG_TEST_URL：跳过 PostgreSQL 实机测试（默认回归不依赖 PG）"
)
requires_pg = unittest.skipUnless(PG_URL, PG_SKIP_REASON)

SCOPE = frozenset({"prj_xinghui"})
LEASE = "lease_xh_a301_2025"

BUSINESS_TABLES = (
    "projects",
    "buildings",
    "units",
    "tenants",
    "leases",
    "lease_charge_rules",
    "invoices",
    "invoice_items",
    "payments",
    "payment_allocations",
    "work_orders",
    "documents",
)


def _fixture() -> FixtureRepository:
    return FixtureRepository.load()


def _migrate(action: str, target: str) -> None:
    """在 PG 测试库上执行一次 alembic 动作。

    `migrations/env.py` 优先读取 `COMMERCIAL_DB_URL`；临时指向 PG 测试库，
    结束后恢复，避免误迁移到其他数据库或污染其他测试。
    """

    previous = os.environ.get("COMMERCIAL_DB_URL")
    os.environ["COMMERCIAL_DB_URL"] = PG_URL
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", PG_URL)
        getattr(command, action)(config, target)
    finally:
        if previous is None:
            os.environ.pop("COMMERCIAL_DB_URL", None)
        else:
            os.environ["COMMERCIAL_DB_URL"] = previous


def _reset_database() -> None:
    _migrate("downgrade", "base")
    _migrate("upgrade", "head")


def _public_tables(engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            ).scalars()
        )


def _numeric_column(engine, table: str, column: str) -> tuple[str, int | None, int | None]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table "
                "AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).one()
    return row[0], row[1], row[2]


@requires_pg
class TestMigrationsPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine_for(PG_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        _migrate("downgrade", "base")

    def setUp(self) -> None:
        _reset_database()

    def tearDown(self) -> None:
        _migrate("downgrade", "base")

    def test_upgrade_head_creates_business_tables(self) -> None:
        tables = _public_tables(self.engine)
        self.assertEqual(tables, set(BUSINESS_TABLES) | {"alembic_version"})

    def test_numeric_precision_after_upgrade(self) -> None:
        four_decimals = (
            ("lease_charge_rules", "unit_price"),
            ("invoice_items", "unit_price"),
            ("invoice_items", "quantity"),
        )
        two_decimals = (
            ("lease_charge_rules", "amount"),
            ("invoice_items", "amount"),
            ("payments", "amount"),
            ("payment_allocations", "amount"),
        )
        for table, column in four_decimals:
            with self.subTest(table=table, column=column):
                data_type, precision, scale = _numeric_column(self.engine, table, column)
                self.assertEqual(data_type, "numeric")
                self.assertEqual(precision, 14)
                self.assertEqual(scale, 4)
        for table, column in two_decimals:
            with self.subTest(table=table, column=column):
                data_type, precision, scale = _numeric_column(self.engine, table, column)
                self.assertEqual(data_type, "numeric")
                self.assertEqual(precision, 14)
                self.assertEqual(scale, 2)

    def test_0002_downgrade_narrows_then_upgrade_widens(self) -> None:
        """证明 0002 是真实 DDL：降到 0001 后是 2 位，再升级回到 4 位。"""

        _migrate("downgrade", "0001")
        for table, column in (
            ("lease_charge_rules", "unit_price"),
            ("invoice_items", "unit_price"),
            ("invoice_items", "quantity"),
        ):
            with self.subTest(table=table, column=column):
                self.assertEqual(_numeric_column(self.engine, table, column)[2], 2)

        _migrate("upgrade", "head")
        for table, column in (
            ("lease_charge_rules", "unit_price"),
            ("invoice_items", "unit_price"),
            ("invoice_items", "quantity"),
        ):
            with self.subTest(table=table, column=column):
                self.assertEqual(_numeric_column(self.engine, table, column)[2], 4)

    def test_downgrade_base_drops_business_tables(self) -> None:
        _migrate("downgrade", "base")
        remaining = _public_tables(self.engine)
        self.assertFalse(set(BUSINESS_TABLES) & remaining, set(BUSINESS_TABLES) & remaining)


class _SeededPostgresCase(unittest.TestCase):
    """每个测试类自建 / 清库，并装配一份只读仓库。"""

    engine = None
    repository = None

    @classmethod
    def setUpClass(cls) -> None:
        _reset_database()
        cls.engine = create_engine_for(PG_URL)
        cls.repository = build_repository_for_engine(cls.engine, create_tables=False)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.repository is not None:
            cls.repository._session.close()  # noqa: SLF001 - 测试装配结果本身
        if cls.engine is not None:
            cls.engine.dispose()
        _migrate("downgrade", "base")


@requires_pg
class TestSeedPostgres(_SeededPostgresCase):
    def test_seed_row_counts_match_fixture(self) -> None:
        fixture = _fixture()
        with self.engine.connect() as connection:
            counts = {
                table: connection.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar_one()
                for table in BUSINESS_TABLES
            }
        snapshot = fixture.snapshot()
        for table in BUSINESS_TABLES:
            with self.subTest(table=table):
                self.assertEqual(counts[table], len(snapshot[table]))
        self.assertEqual(self.repository.dataset_version, fixture.dataset_version)


@requires_pg
class TestEquivalenceWithFixturePostgres(_SeededPostgresCase):
    """同一 fixture 在 PG 与 fixture 仓库上必须返回等价事实。"""

    def test_arrears_amounts_match(self) -> None:
        fixture = _fixture()
        expected = fixture.arrears(project_ids=SCOPE, lease_id=LEASE)
        actual = self.repository.arrears(project_ids=SCOPE, lease_id=LEASE)

        for key in ("invoiced_total", "paid_total", "outstanding_total"):
            self.assertEqual(
                Decimal(str(actual[key])), Decimal(str(expected[key])), key
            )
        self.assertEqual(Decimal(str(actual["rent_variance_total"])), Decimal("756.00"))
        self.assertEqual(
            actual["outstanding_invoice_ids"], expected["outstanding_invoice_ids"]
        )

    def test_statement_allocations_and_payments_match(self) -> None:
        expected = _fixture().statement(project_ids=SCOPE, lease_id=LEASE)
        actual = self.repository.statement(project_ids=SCOPE, lease_id=LEASE)

        self.assertEqual(
            {item["id"] for item in actual["allocations"]},
            {item["id"] for item in expected["allocations"]},
        )
        self.assertEqual(
            {item["id"] for item in actual["payments"]},
            {item["id"] for item in expected["payments"]},
        )
        self.assertEqual(len(actual["invoices"]), len(expected["invoices"]))

    def test_payment_timestamps_keep_dataset_offset(self) -> None:
        expected = {
            item["id"]: item["paid_at"]
            for item in _fixture().statement(project_ids=SCOPE, lease_id=LEASE)["payments"]
        }
        actual = {
            item["id"]: item["paid_at"]
            for item in self.repository.statement(
                project_ids=SCOPE, lease_id=LEASE
            )["payments"]
        }
        self.assertTrue(actual, "应至少有一笔已确认收款")
        self.assertEqual(actual, expected)
        for value in actual.values():
            self.assertTrue(value.endswith("+08:00"), value)

    def test_lease_facts_match(self) -> None:
        expected = _fixture().lease_facts(project_ids=SCOPE, lease_id=LEASE)
        actual = self.repository.lease_facts(project_ids=SCOPE, lease_id=LEASE)

        self.assertEqual(actual["lease"]["start_date"], expected["lease"]["start_date"])
        self.assertEqual(actual["lease"]["end_date"], expected["lease"]["end_date"])
        self.assertEqual(actual["lease"]["status"], expected["lease"]["status"])
        self.assertEqual(
            {rule["id"] for rule in actual["rules"]},
            {rule["id"] for rule in expected["rules"]},
        )
        self.assertEqual(actual["missing_documents"], ["doc_xh_a301_annex_b"])
        self.assertEqual(actual["missing_documents"], expected["missing_documents"])

    def test_work_orders_and_timestamps_match(self) -> None:
        expected = {
            item["id"]: item
            for item in _fixture().work_orders(
                project_ids=SCOPE, lease_id=LEASE, category="hvac"
            )
        }
        actual = {
            item["id"]: item
            for item in self.repository.work_orders(
                project_ids=SCOPE, lease_id=LEASE, category="hvac"
            )
        }
        self.assertTrue(actual)
        self.assertEqual(set(actual), set(expected))
        for order_id, expected_order in expected.items():
            with self.subTest(order_id=order_id):
                self.assertEqual(
                    actual[order_id]["reported_at"], expected_order["reported_at"]
                )
                self.assertEqual(
                    actual[order_id]["resolved_at"], expected_order["resolved_at"]
                )
                self.assertTrue(
                    actual[order_id]["reported_at"].endswith("+08:00"),
                    actual[order_id]["reported_at"],
                )

    def test_unit_price_keeps_four_decimals(self) -> None:
        snapshot = _fixture().snapshot()
        with Session(self.engine) as session:
            rules = {
                rule.id: str(rule.unit_price)
                for rule in session.scalars(select(LeaseChargeRule))
            }
            items = {
                item.id: (str(item.quantity), str(item.unit_price), str(item.amount))
                for item in session.scalars(select(InvoiceItem))
            }

        self.assertEqual(
            rules,
            {rule["id"]: rule["unit_price"] for rule in snapshot["lease_charge_rules"]},
        )
        self.assertEqual(
            items,
            {
                item["id"]: (item["quantity"], item["unit_price"], item["amount"])
                for item in snapshot["invoice_items"]
            },
        )
        self.assertIn("132.3000", rules.values())

    def test_connections_use_dataset_timezone(self) -> None:
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(text("SHOW TIME ZONE")).scalar_one(),
                DATASET_TIMEZONE,
            )
        self.assertEqual(
            self.repository._session.execute(  # noqa: SLF001 - 断言只读会话本身
                text("SHOW TIME ZONE")
            ).scalar_one(),
            DATASET_TIMEZONE,
        )


@requires_pg
class TestReadOnlyPostgres(_SeededPostgresCase):
    """只读必须覆盖会话的整个生命周期，而不只是第一个事务。"""

    @staticmethod
    def _insert_project(session: Session) -> None:
        session.execute(
            text(
                "INSERT INTO projects (id, code, name, timezone, status) "
                "VALUES ('pg_readonly_probe', 'PGRO', 'probe', 'UTC', 'active')"
            )
        )

    def test_first_transaction_rejects_write_then_reads(self) -> None:
        with session_scope(self.engine, read_only=True) as session:
            with self.assertRaises(DBAPIError):
                self._insert_project(session)
            session.rollback()
            self.assertTrue(
                session.execute(text("SELECT COUNT(*) FROM projects")).scalar_one() > 0
            )

    def test_transaction_after_rollback_still_rejects_write(self) -> None:
        with session_scope(self.engine, read_only=True) as session:
            session.execute(text("SELECT 1"))
            session.rollback()
            with self.assertRaises(DBAPIError):
                self._insert_project(session)
            session.rollback()
            self.assertTrue(
                session.execute(text("SELECT COUNT(*) FROM projects")).scalar_one() > 0
            )

    def test_transaction_after_commit_still_rejects_write(self) -> None:
        with session_scope(self.engine, read_only=True) as session:
            session.execute(text("SELECT 1"))
            session.commit()
            with self.assertRaises(DBAPIError):
                self._insert_project(session)
            session.rollback()
            self.assertTrue(
                session.execute(text("SELECT COUNT(*) FROM units")).scalar_one() > 0
            )


@requires_pg
class TestRepositoryIsolationPostgres(_SeededPostgresCase):
    def test_cross_project_access_is_denied(self) -> None:
        with self.assertRaises(AgentError) as ctx:
            self.repository.arrears(project_ids=SCOPE, lease_id="lease_jl_b101_2025")
        self.assertEqual(ctx.exception.code, ErrorCode.PROJECT_SCOPE_DENIED)

    def test_unknown_lease_is_not_found(self) -> None:
        with self.assertRaises(AgentError) as ctx:
            self.repository.arrears(project_ids=SCOPE, lease_id="lease_does_not_exist")
        self.assertEqual(ctx.exception.code, ErrorCode.RECORD_NOT_FOUND)

    def test_amounts_are_decimal_not_float(self) -> None:
        statement = self.repository.statement(project_ids=SCOPE, lease_id=LEASE)
        amounts = [
            statement["invoiced_total"],
            statement["paid_total"],
            statement["outstanding_total"],
            statement["rent_variance_total"],
        ]
        for view in statement["invoices"]:
            amounts.extend([view["total"], view["allocated"], view["outstanding"]])
        for value in amounts:
            with self.subTest(value=value):
                self.assertIsInstance(value, Decimal)
                self.assertNotIsInstance(value, float)
        # 明细金额按 fixture 的外形输出为十进制字符串，且保持 2 位小数。
        for view in statement["invoices"]:
            for item in view["items"]:
                with self.subTest(item=item["id"]):
                    self.assertRegex(item["amount"], r"^-?\d+\.\d{2}$")


@requires_pg
class TestToolsBoundToPostgres(_SeededPostgresCase):
    def test_investigation_uses_postgres_repository(self) -> None:
        """工具层不修改即可指向 PG 仓库；关键数字与 fixture 路径一致。"""

        import asyncio

        from app.orchestration.investigation import Investigator
        from app.tools.fixture_tools import build_fixture_tools
        from app.tools.registry import ToolRegistry

        tool_registry = ToolRegistry()
        for tool in build_fixture_tools(self.repository):
            tool_registry.register(tool)

        budget = Budget(max_tool_calls=12)
        trace_log = TraceLog()
        report = build_registry(
            tool_registry=tool_registry, budget=budget, trace_log=trace_log
        )
        investigator = Investigator(registry=report.registry, repository=self.repository)
        context = AgentContext(
            trace_id="trace_pg",
            run_id="run_pg",
            principal_id="principal_ops_xinghui",
            project_ids=SCOPE,
            permissions=frozenset(
                {"lease.read", "billing.read", "property.read", "approval.request"}
            ),
        )
        result = asyncio.run(
            investigator.investigate(
                question=(
                    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
                    "并要求减免费用。请核对合同、账单、付款和工单。"
                ),
                lease_id=LEASE,
                context=context,
            )
        )
        self.assertEqual(result.verdict, "conflicting")
        self.assertEqual(Decimal(result.conflicts[0]["amount"]), Decimal("756.00"))
        arrears = self.repository.arrears(project_ids=SCOPE, lease_id=LEASE)
        self.assertEqual(Decimal(arrears["outstanding_total"]), Decimal("18036.00"))
        fixture_arrears = _fixture().arrears(project_ids=SCOPE, lease_id=LEASE)
        self.assertEqual(
            Decimal(arrears["outstanding_total"]),
            Decimal(str(fixture_arrears["outstanding_total"])),
        )
        self.assertTrue(any("18036.00" in f["statement"] for f in result.report["findings"]))
        lease_result = next(
            item for item in result.results if item["capability"] == "lease.query"
        )
        self.assertEqual(lease_result["status"], "partial")
        self.assertTrue(
            any("条款检索不可用" in warning for warning in lease_result["warnings"])
        )
        self.assertGreaterEqual(len(trace_log.snapshot()), 3)


# ---------------------------------------------------------------- Task 035B


P0_CONSTRAINT_NAMES = (
    "ck_projects_status_p0",
    "ck_units_area_positive_p0",
    "ck_units_chargeable_area_positive_p0",
    "ck_units_physical_status_p0",
    "ck_tenants_status_p0",
    "ck_leases_status_p0",
    "ck_leases_billing_cycle_p0",
    "ck_leases_date_range_p0",
    "ck_leases_payment_terms_days_p0",
    "ck_leases_deposit_non_negative_p0",
    "ck_leases_currency_format_p0",
    "ck_charge_rules_charge_type_p0",
    "ck_charge_rules_calculation_method_p0",
    "ck_charge_rules_period_unit_p0",
    "ck_charge_rules_amount_non_negative_p0",
    "ck_charge_rules_unit_price_non_negative_p0",
    "ck_charge_rules_effective_range_p0",
    "ck_charge_rules_calc_consistency_p0",
    "ck_invoices_period_range_p0",
    "ck_invoices_due_after_issue_p0",
    "ck_invoices_status_p0",
    "ck_invoices_currency_format_p0",
    "ck_invoice_items_charge_type_p0",
    "ck_invoice_items_amount_adjustment_p0",
    "ck_invoice_items_quantity_nonzero_p0",
    "ck_invoice_items_unit_price_non_negative_p0",
    "ck_payments_amount_positive_p0",
    "ck_payments_status_p0",
    "ck_payments_method_p0",
    "ck_payments_currency_format_p0",
    "ck_payment_allocations_amount_positive_p0",
    "ck_work_orders_category_p0",
    "ck_work_orders_priority_p0",
    "ck_work_orders_status_p0",
    "ck_work_orders_resolved_after_reported_p0",
    "ck_work_orders_resolved_status_time_p0",
    "ck_documents_doc_type_p0",
    "ck_documents_version_positive_p0",
    "ck_documents_status_p0",
)
EXCLUSION_CONSTRAINT_NAME = "ex_leases_unit_active_period_p0"


@requires_pg
class TestP0ConstraintsPostgres(_SeededPostgresCase):
    """每类 P0 约束都构造一条违规写入，由数据库拒绝；fixture seed 本身仍成功。"""

    def _assert_rejected(self, sql: str, constraint: str | tuple[str, ...]) -> None:
        names = (constraint,) if isinstance(constraint, str) else constraint
        with Session(self.engine) as session:
            with self.assertRaises(DBAPIError) as ctx:
                session.execute(text(sql))
            message = str(ctx.exception.orig)
            self.assertTrue(
                any(name in message for name in names),
                f"期望违反 {names}，实际错误: {message}",
            )
            session.rollback()

    def _assert_accepted(self, sql: str) -> None:
        with Session(self.engine) as session:
            session.execute(text(sql))
            session.rollback()

    def test_fixture_seed_satisfies_all_constraints(self) -> None:
        """类级 seed 已带约束执行；这里再核对行数与 fixture 一致。"""

        snapshot = _fixture().snapshot()
        with self.engine.connect() as connection:
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in BUSINESS_TABLES
            }
        for table in BUSINESS_TABLES:
            with self.subTest(table=table):
                self.assertEqual(counts[table], len(snapshot[table]))

    def test_constraint_names_are_installed(self) -> None:
        with self.engine.connect() as connection:
            names = set(
                connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conname ~ '^(ck|ex)_' AND connamespace = 'public'::regnamespace"
                    )
                ).scalars()
            )
        self.assertEqual(set(P0_CONSTRAINT_NAMES) - names, set())
        self.assertIn(EXCLUSION_CONSTRAINT_NAME, names)

    def test_invalid_rows_are_rejected(self) -> None:
        lease_columns = (
            "INSERT INTO leases (id, project_id, lease_no, tenant_id, unit_id, "
            "start_date, end_date, status, billing_cycle, payment_terms_days, "
            "deposit_amount, currency) VALUES "
        )
        cases = [
            (
                "projects.status",
                "INSERT INTO projects (id, code, name, timezone, status) VALUES "
                "('probe_prj_status', 'PROBE-PRJ', 'probe', 'Asia/Shanghai', 'archivedx')",
                "ck_projects_status_p0",
            ),
            (
                "units.area_sqm",
                "INSERT INTO units (id, project_id, building_id, code, area_sqm, "
                "chargeable_area_sqm, physical_status) VALUES ('probe_unit_area', "
                "'prj_xinghui', 'bld_xh_a', 'PROBE-AREA', '0.00', '10.00', 'normal')",
                "ck_units_area_positive_p0",
            ),
            (
                "units.chargeable_area_sqm",
                "INSERT INTO units (id, project_id, building_id, code, area_sqm, "
                "chargeable_area_sqm, physical_status) VALUES ('probe_unit_chg', "
                "'prj_xinghui', 'bld_xh_a', 'PROBE-CHG', '10.00', '0.00', 'normal')",
                "ck_units_chargeable_area_positive_p0",
            ),
            (
                "units.physical_status",
                "INSERT INTO units (id, project_id, building_id, code, area_sqm, "
                "chargeable_area_sqm, physical_status) VALUES ('probe_unit_status', "
                "'prj_xinghui', 'bld_xh_a', 'PROBE-UST', '10.00', '10.00', 'broken')",
                "ck_units_physical_status_p0",
            ),
            (
                "tenants.status",
                "INSERT INTO tenants (id, code, name, status) VALUES "
                "('probe_tenant_status', 'PROBE-TEN', 'probe', 'unknown')",
                "ck_tenants_status_p0",
            ),
            (
                "leases.status",
                lease_columns
                + "('probe_lease_status', 'prj_xinghui', 'PROBE-LST', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', '2026-12-31', "
                "'unknown', 'monthly', 30, '0.00', 'CNY')",
                "ck_leases_status_p0",
            ),
            (
                "leases.billing_cycle",
                lease_columns
                + "('probe_lease_cycle', 'prj_xinghui', 'PROBE-LCY', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', '2026-12-31', "
                "'draft', 'weekly', 30, '0.00', 'CNY')",
                "ck_leases_billing_cycle_p0",
            ),
            (
                "leases.end_date < start_date",
                lease_columns
                + "('probe_lease_date', 'prj_xinghui', 'PROBE-LDT', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-12-31', '2026-01-01', "
                "'draft', 'monthly', 30, '0.00', 'CNY')",
                "ck_leases_date_range_p0",
            ),
            (
                "leases.payment_terms_days",
                lease_columns
                + "('probe_lease_terms', 'prj_xinghui', 'PROBE-LTM', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', '2026-12-31', "
                "'draft', 'monthly', 181, '0.00', 'CNY')",
                "ck_leases_payment_terms_days_p0",
            ),
            (
                "leases.deposit_amount",
                lease_columns
                + "('probe_lease_dep', 'prj_xinghui', 'PROBE-LDP', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', '2026-12-31', "
                "'draft', 'monthly', 30, '-1.00', 'CNY')",
                "ck_leases_deposit_non_negative_p0",
            ),
            (
                "leases.currency",
                lease_columns
                + "('probe_lease_ccy', 'prj_xinghui', 'PROBE-LCC', "
                "'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', '2026-12-31', "
                "'draft', 'monthly', 30, '0.00', 'cny')",
                "ck_leases_currency_format_p0",
            ),
            (
                "lease_charge_rules.charge_type",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_type', "
                "'lease_xh_a301_2025', 'deposit', 'per_sqm', NULL, '1.0000', "
                "'month', '2026-01-01', '2026-12-31', false)",
                "ck_charge_rules_charge_type_p0",
            ),
            (
                "lease_charge_rules.calculation_method",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_calc', "
                "'lease_xh_a301_2025', 'rent', 'per_day', NULL, '1.0000', 'month', "
                "'2026-01-01', '2026-12-31', false)",
                ("ck_charge_rules_calculation_method_p0",
                 "ck_charge_rules_calc_consistency_p0"),
            ),
            (
                "lease_charge_rules.period_unit",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_unit', "
                "'lease_xh_a301_2025', 'rent', 'per_sqm', NULL, '1.0000', 'week', "
                "'2026-01-01', '2026-12-31', false)",
                "ck_charge_rules_period_unit_p0",
            ),
            (
                "lease_charge_rules.amount",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_amt', "
                "'lease_xh_a301_2025', 'rent', 'fixed_amount', '-1.00', NULL, "
                "'month', '2026-01-01', '2026-12-31', false)",
                "ck_charge_rules_amount_non_negative_p0",
            ),
            (
                "lease_charge_rules.unit_price",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_price', "
                "'lease_xh_a301_2025', 'rent', 'per_sqm', NULL, '-1.0000', 'month', "
                "'2026-01-01', '2026-12-31', false)",
                "ck_charge_rules_unit_price_non_negative_p0",
            ),
            (
                "lease_charge_rules.effective_range",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_range', "
                "'lease_xh_a301_2025', 'rent', 'per_sqm', NULL, '1.0000', 'month', "
                "'2026-12-31', '2026-01-01', false)",
                "ck_charge_rules_effective_range_p0",
            ),
            (
                "lease_charge_rules.calc_consistency",
                "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
                "calculation_method, amount, unit_price, period_unit, effective_from, "
                "effective_to, is_rent_free) VALUES ('probe_rule_cons', "
                "'lease_xh_a301_2025', 'rent', 'fixed_amount', NULL, '1.0000', "
                "'month', '2026-01-01', '2026-12-31', false)",
                "ck_charge_rules_calc_consistency_p0",
            ),
            (
                "invoices.period_range",
                "INSERT INTO invoices (id, project_id, lease_id, invoice_no, "
                "period_start, period_end, issue_date, due_date, currency, status) "
                "VALUES ('probe_inv_period', 'prj_xinghui', 'lease_xh_a301_2025', "
                "'PROBE-INV-P', '2026-12-31', '2026-01-01', '2026-01-01', "
                "'2026-01-02', 'CNY', 'draft')",
                "ck_invoices_period_range_p0",
            ),
            (
                "invoices.due_date",
                "INSERT INTO invoices (id, project_id, lease_id, invoice_no, "
                "period_start, period_end, issue_date, due_date, currency, status) "
                "VALUES ('probe_inv_due', 'prj_xinghui', 'lease_xh_a301_2025', "
                "'PROBE-INV-D', '2026-01-01', '2026-01-31', '2026-01-31', "
                "'2026-01-01', 'CNY', 'draft')",
                "ck_invoices_due_after_issue_p0",
            ),
            (
                "invoices.status",
                "INSERT INTO invoices (id, project_id, lease_id, invoice_no, "
                "period_start, period_end, issue_date, due_date, currency, status) "
                "VALUES ('probe_inv_status', 'prj_xinghui', 'lease_xh_a301_2025', "
                "'PROBE-INV-S', '2026-01-01', '2026-01-31', '2026-01-31', "
                "'2026-01-31', 'CNY', 'paid')",
                "ck_invoices_status_p0",
            ),
            (
                "invoices.currency",
                "INSERT INTO invoices (id, project_id, lease_id, invoice_no, "
                "period_start, period_end, issue_date, due_date, currency, status) "
                "VALUES ('probe_inv_ccy', 'prj_xinghui', 'lease_xh_a301_2025', "
                "'PROBE-INV-C', '2026-01-01', '2026-01-31', '2026-01-31', "
                "'2026-01-31', 'cny', 'draft')",
                "ck_invoices_currency_format_p0",
            ),
            (
                "invoice_items.charge_type",
                "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
                "quantity, unit_price, amount) VALUES ('probe_item_type', "
                "'inv_2026_08', 'tax', 'probe', '1.0000', '1.0000', '1.00')",
                "ck_invoice_items_charge_type_p0",
            ),
            (
                "invoice_items.amount",
                "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
                "quantity, unit_price, amount) VALUES ('probe_item_amt', "
                "'inv_2026_08', 'rent', 'probe', '1.0000', '1.0000', '-1.00')",
                "ck_invoice_items_amount_adjustment_p0",
            ),
            (
                "invoice_items.quantity",
                "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
                "quantity, unit_price, amount) VALUES ('probe_item_qty', "
                "'inv_2026_08', 'rent', 'probe', '0.0000', '1.0000', '1.00')",
                "ck_invoice_items_quantity_nonzero_p0",
            ),
            (
                "invoice_items.unit_price",
                "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
                "quantity, unit_price, amount) VALUES ('probe_item_price', "
                "'inv_2026_08', 'rent', 'probe', '1.0000', '-1.0000', '1.00')",
                "ck_invoice_items_unit_price_non_negative_p0",
            ),
            (
                "payments.amount",
                "INSERT INTO payments (id, project_id, receipt_no, payment_method, "
                "amount, currency, paid_at, status) VALUES ('probe_pay_amt', "
                "'prj_xinghui', 'PROBE-PAY-A', 'bank_transfer', '0.00', 'CNY', "
                "'2026-01-01T00:00:00+08:00', 'confirmed')",
                "ck_payments_amount_positive_p0",
            ),
            (
                "payments.status",
                "INSERT INTO payments (id, project_id, receipt_no, payment_method, "
                "amount, currency, paid_at, status) VALUES ('probe_pay_status', "
                "'prj_xinghui', 'PROBE-PAY-S', 'bank_transfer', '1.00', 'CNY', "
                "'2026-01-01T00:00:00+08:00', 'paid')",
                "ck_payments_status_p0",
            ),
            (
                "payments.payment_method",
                "INSERT INTO payments (id, project_id, receipt_no, payment_method, "
                "amount, currency, paid_at, status) VALUES ('probe_pay_method', "
                "'prj_xinghui', 'PROBE-PAY-M', 'wire', '1.00', 'CNY', "
                "'2026-01-01T00:00:00+08:00', 'confirmed')",
                "ck_payments_method_p0",
            ),
            (
                "payments.currency",
                "INSERT INTO payments (id, project_id, receipt_no, payment_method, "
                "amount, currency, paid_at, status) VALUES ('probe_pay_ccy', "
                "'prj_xinghui', 'PROBE-PAY-C', 'bank_transfer', '1.00', 'CN', "
                "'2026-01-01T00:00:00+08:00', 'confirmed')",
                "ck_payments_currency_format_p0",
            ),
            (
                "payment_allocations.amount",
                "INSERT INTO payment_allocations (id, payment_id, invoice_id, amount, "
                "allocated_at) VALUES ('probe_alloc_amt', 'pay_2026_09_28', "
                "'inv_2026_10', '0.00', '2026-01-01T00:00:00+08:00')",
                "ck_payment_allocations_amount_positive_p0",
            ),
            (
                "work_orders.category",
                "INSERT INTO work_orders (id, project_id, work_order_no, category, "
                "priority, status, title, reported_at) VALUES ('probe_wo_cat', "
                "'prj_xinghui', 'PROBE-WO-C', 'roof', 'normal', 'open', 'probe', "
                "'2026-01-01T00:00:00+08:00')",
                "ck_work_orders_category_p0",
            ),
            (
                "work_orders.priority",
                "INSERT INTO work_orders (id, project_id, work_order_no, category, "
                "priority, status, title, reported_at) VALUES ('probe_wo_pri', "
                "'prj_xinghui', 'PROBE-WO-P', 'hvac', 'critical', 'open', 'probe', "
                "'2026-01-01T00:00:00+08:00')",
                "ck_work_orders_priority_p0",
            ),
            (
                "work_orders.status",
                "INSERT INTO work_orders (id, project_id, work_order_no, category, "
                "priority, status, title, reported_at) VALUES ('probe_wo_status', "
                "'prj_xinghui', 'PROBE-WO-S', 'hvac', 'normal', 'done', 'probe', "
                "'2026-01-01T00:00:00+08:00')",
                "ck_work_orders_status_p0",
            ),
            (
                "work_orders.resolved_at < reported_at",
                "INSERT INTO work_orders (id, project_id, work_order_no, category, "
                "priority, status, title, reported_at, resolved_at) VALUES "
                "('probe_wo_time', 'prj_xinghui', 'PROBE-WO-T', 'hvac', 'normal', "
                "'in_progress', 'probe', '2026-02-02T10:00:00+08:00', "
                "'2026-02-01T10:00:00+08:00')",
                "ck_work_orders_resolved_after_reported_p0",
            ),
            (
                "work_orders.status/resolved_at",
                "INSERT INTO work_orders (id, project_id, work_order_no, category, "
                "priority, status, title, reported_at) VALUES ('probe_wo_closed', "
                "'prj_xinghui', 'PROBE-WO-X', 'hvac', 'normal', 'closed', 'probe', "
                "'2026-01-01T00:00:00+08:00')",
                "ck_work_orders_resolved_status_time_p0",
            ),
            (
                "documents.doc_type",
                "INSERT INTO documents (id, project_id, doc_type, title, version, "
                "document_status, checksum_sha256) VALUES ('probe_doc_type', "
                "'prj_xinghui', 'memo', 'probe', 1, 'signed', "
                f"'{'0' * 64}')",
                "ck_documents_doc_type_p0",
            ),
            (
                "documents.version",
                "INSERT INTO documents (id, project_id, doc_type, title, version, "
                "document_status, checksum_sha256) VALUES ('probe_doc_ver', "
                "'prj_xinghui', 'attachment', 'probe', 0, 'signed', "
                f"'{'0' * 64}')",
                "ck_documents_version_positive_p0",
            ),
            (
                "documents.document_status",
                "INSERT INTO documents (id, project_id, doc_type, title, version, "
                "document_status, checksum_sha256) VALUES ('probe_doc_status', "
                "'prj_xinghui', 'attachment', 'probe', 1, 'unsigned', "
                f"'{'0' * 64}')",
                "ck_documents_status_p0",
            ),
        ]
        for label, sql, constraint in cases:
            with self.subTest(case=label):
                self._assert_rejected(sql, constraint)

    def test_other_fee_negative_amount_is_allowed(self) -> None:
        """设计允许调整类明细为负数（减免/冲抵）；fixture 暂无此类行。"""

        self._assert_accepted(
            "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
            "quantity, unit_price, amount) VALUES ('probe_item_adjust', "
            "'inv_2026_08', 'other_fee', 'probe adjustment', '1.0000', NULL, '-1.00')"
        )


@requires_pg
class TestLeaseExclusionPostgres(_SeededPostgresCase):
    """同一商铺的生效租约期间不得重叠（PG EXCLUDE）。"""

    _LEASE_COLUMNS = (
        "INSERT INTO leases (id, project_id, lease_no, tenant_id, unit_id, "
        "start_date, end_date, status, billing_cycle, payment_terms_days, "
        "deposit_amount, currency) VALUES "
    )

    def _insert(self, *, row_id: str, lease_no: str, start: str, end: str, status: str) -> None:
        with Session(self.engine) as session:
            session.execute(
                text(
                    self._LEASE_COLUMNS
                    + "(:id, 'prj_xinghui', :no, 'ten_xh_yunduan', 'unit_xh_a301', "
                    ":start, :end, :status, 'monthly', 30, '0.00', 'CNY')"
                ),
                {
                    "id": row_id,
                    "no": lease_no,
                    "start": start,
                    "end": end,
                    "status": status,
                },
            )
            session.rollback()

    def test_active_overlap_is_rejected(self) -> None:
        with Session(self.engine) as session:
            with self.assertRaises(DBAPIError) as ctx:
                session.execute(
                    text(
                        self._LEASE_COLUMNS
                        + "('probe_overlap', 'prj_xinghui', 'PROBE-OVL', "
                        "'ten_xh_yunduan', 'unit_xh_a301', '2026-06-01', "
                        "'2026-12-31', 'active', 'monthly', 30, '0.00', 'CNY')"
                    )
                )
            self.assertIn(EXCLUSION_CONSTRAINT_NAME, str(ctx.exception.orig))
            session.rollback()

    def test_non_overlapping_active_lease_is_allowed(self) -> None:
        self._insert(
            row_id="probe_no_overlap",
            lease_no="PROBE-NOV",
            start="2028-01-01",
            end="2028-12-31",
            status="active",
        )

    def test_overlap_with_non_active_status_is_allowed(self) -> None:
        self._insert(
            row_id="probe_draft_overlap",
            lease_no="PROBE-DRF",
            start="2026-06-01",
            end="2026-12-31",
            status="draft",
        )

    # 复查 P3-1：把闭区间 `[]` 的选择固化下来。现有 A-301 生效租约为 2025-01-01 ~ 2027-12-31。
    def test_same_day_handover_is_rejected(self) -> None:
        """新租约起始日 = 旧租约结束日：闭区间下两天重叠，必须拒绝（开区间 `[)` 会放行）。"""

        with Session(self.engine) as session:
            with self.assertRaises(DBAPIError) as ctx:
                session.execute(
                    text(
                        self._LEASE_COLUMNS
                        + "('probe_same_day', 'prj_xinghui', 'PROBE-SAME', "
                        "'ten_xh_yunduan', 'unit_xh_a301', '2027-12-31', "
                        "'2028-06-30', 'active', 'monthly', 30, '0.00', 'CNY')"
                    )
                )
            self.assertIn(EXCLUSION_CONSTRAINT_NAME, str(ctx.exception.orig))
            session.rollback()

    def test_next_day_handover_is_allowed(self) -> None:
        self._insert(
            row_id="probe_next_day",
            lease_no="PROBE-NEXT",
            start="2028-01-01",
            end="2028-06-30",
            status="active",
        )

    def test_activating_overlapping_draft_is_rejected(self) -> None:
        """草案可以与生效租约重叠，但把它改成 active 的那一刻必须被拒绝（更新路径）。"""

        with Session(self.engine) as session:
            session.execute(
                text(
                    self._LEASE_COLUMNS
                    + "('probe_draft_to_active', 'prj_xinghui', 'PROBE-D2A', "
                    "'ten_xh_yunduan', 'unit_xh_a301', '2026-06-01', "
                    "'2026-12-31', 'draft', 'monthly', 30, '0.00', 'CNY')"
                )
            )
            with self.assertRaises(DBAPIError) as ctx:
                session.execute(
                    text("UPDATE leases SET status = 'active' WHERE id = 'probe_draft_to_active'")
                )
            self.assertIn(EXCLUSION_CONSTRAINT_NAME, str(ctx.exception.orig))
            session.rollback()


@requires_pg
class TestReadonlyRolePostgres(_SeededPostgresCase):
    """只有 SELECT 权限的数据库角色：读得到业务数据，任何写入都被拒绝。"""

    def test_readonly_role_can_read_but_never_write(self) -> None:
        import secrets

        from sqlalchemy.engine import make_url

        from app.db.roles import create_readonly_role, drop_readonly_role

        role_name = f"ro_probe_{secrets.token_hex(4)}"
        password = secrets.token_hex(16)
        create_readonly_role(self.engine, role_name, password)
        role_engine = None
        try:
            role_url = (
                make_url(PG_URL)
                .set(username=role_name, password=password)
                .render_as_string(hide_password=False)
            )
            role_engine = create_engine_for(role_url)
            with role_engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT COUNT(*) FROM invoices")).scalar_one(),
                    len(_fixture().snapshot()["invoices"]),
                )
                self.assertEqual(
                    connection.execute(text("SHOW TIME ZONE")).scalar_one(),
                    DATASET_TIMEZONE,
                )

            writes = (
                "INSERT INTO projects (id, code, name, timezone, status) "
                "VALUES ('ro_probe', 'ROPROBE', 'probe', 'UTC', 'active')",
                "UPDATE invoices SET currency = currency WHERE 1 = 0",
                "DELETE FROM payments WHERE 1 = 0",
                "CREATE TABLE ro_probe_table (id integer)",
            )
            for statement in writes:
                with self.subTest(statement=statement):
                    with self.assertRaises(DBAPIError):
                        with role_engine.begin() as connection:
                            connection.execute(text(statement))

            # 显式把事务改成可写也没用：权限边界不是会话级只读设置。
            with self.assertRaises(DBAPIError):
                with role_engine.begin() as connection:
                    connection.execute(text("SET TRANSACTION READ WRITE"))
                    connection.execute(
                        text(
                            "INSERT INTO projects (id, code, name, timezone, status) "
                            "VALUES ('ro_probe_rw', 'ROPROBERW', 'probe', 'UTC', 'active')"
                        )
                    )

            # 被拒后仍可继续读。
            with role_engine.connect() as connection:
                self.assertGreater(
                    connection.execute(text("SELECT COUNT(*) FROM units")).scalar_one(), 0
                )
        finally:
            if role_engine is not None:
                role_engine.dispose()
            drop_readonly_role(self.engine, role_name)

    def test_role_name_is_validated(self) -> None:
        from app.db.roles import create_readonly_role, drop_readonly_role

        for bad_name in ("Upper", "1starts_with_digit", "has-dash", "x; DROP ROLE y", ""):
            with self.subTest(name=bad_name):
                with self.assertRaises(ValueError):
                    create_readonly_role(self.engine, bad_name, "secret")
                with self.assertRaises(ValueError):
                    drop_readonly_role(self.engine, bad_name)

    def test_password_with_special_characters_can_login(self) -> None:
        """密码含 `:x`、`%`、`'`、`\\` 时仍能建角色并登录。

        这些字符分别会触发 SQLAlchemy `text()` 的 `:name` 解析、psycopg 的
        `%` 占位符解析和 SQL 字面量转义问题，必须一次性覆盖。
        """

        import secrets

        from sqlalchemy.engine import make_url

        from app.db.roles import create_readonly_role, drop_readonly_role

        role_name = f"ro_special_{secrets.token_hex(4)}"
        password = "p@ss#:word%quote'back\\slash:tail"
        create_readonly_role(self.engine, role_name, password)
        role_engine = None
        try:
            role_url = (
                make_url(PG_URL)
                .set(username=role_name, password=password)
                .render_as_string(hide_password=False)
            )
            role_engine = create_engine_for(role_url)
            with role_engine.connect() as connection:
                self.assertGreater(
                    connection.execute(text("SELECT COUNT(*) FROM invoices")).scalar_one(), 0
                )
        finally:
            if role_engine is not None:
                role_engine.dispose()
            drop_readonly_role(self.engine, role_name)

    def test_role_creation_failure_never_leaks_password(self) -> None:
        """CREATE ROLE 被数据库拒绝时，异常消息/链不出现密码或 SQL 文本。"""

        import secrets

        from sqlalchemy.engine import make_url

        from app.db.roles import RoleCreationError, create_readonly_role, drop_readonly_role

        creator_name = f"ro_creator_{secrets.token_hex(4)}"
        creator_password = secrets.token_hex(8)
        create_readonly_role(self.engine, creator_name, creator_password)
        limited_engine = None
        try:
            limited_url = (
                make_url(PG_URL)
                .set(username=creator_name, password=creator_password)
                .render_as_string(hide_password=False)
            )
            limited_engine = create_engine_for(limited_url)
            password = "p@ss:word%quote'back\\slash"
            with self.assertRaises(RoleCreationError) as ctx:
                create_readonly_role(
                    limited_engine, f"ro_denied_{secrets.token_hex(4)}", password
                )
            message = str(ctx.exception)
            self.assertNotIn(password, message)
            self.assertNotIn("PASSWORD", message)
            self.assertNotIn("CREATE ROLE", message)
            # 异常在 except 块之外抛出：既没有 __cause__，也没有 __context__（见下），
            # traceback 不会打印带 SQL/密码的原始异常。
            # `raise ... from <原异常>` 同样会把 __suppress_context__ 设为真，但原异常
            # （含 [SQL: CREATE ROLE ... PASSWORD ...]）会进 __cause__ 并被 traceback 打印。
            # 所以还要断言没有 __cause__，并检查完整 traceback 文本（Claude Code 复核补充）。
            import traceback

            self.assertIsNone(ctx.exception.__cause__)
            # 复查 P3-3a：`from None` 只抑制显示，__context__ 仍会留着原异常
            self.assertIsNone(ctx.exception.__context__)
            rendered = "".join(traceback.format_exception(ctx.exception))
            self.assertNotIn(password, rendered)
            self.assertNotIn("CREATE ROLE", rendered)
        finally:
            if limited_engine is not None:
                limited_engine.dispose()
            drop_readonly_role(self.engine, creator_name)

    def test_create_role_refuses_echo_engine(self) -> None:
        """echo=True 会把含密码的 CREATE ROLE 打印到日志，必须拒绝（复查 P3-3b）。"""

        import secrets

        from app.db.roles import create_readonly_role

        echo_engine = create_engine_for(PG_URL, echo=True)
        try:
            with self.assertRaises(ValueError):
                create_readonly_role(echo_engine, f"ro_echo_{secrets.token_hex(4)}", "secret")
            with self.engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'ro_echo_%'")
                    ).scalar_one(),
                    0,
                )
        finally:
            echo_engine.dispose()

    def test_readonly_role_has_no_elevated_attributes(self) -> None:
        """角色属性也是权限边界：不能是超级用户，也不能建库 / 建角色 / 绕过 RLS（复核补充）。"""

        import secrets

        from app.db.roles import create_readonly_role, drop_readonly_role

        role_name = f"ro_attrs_{secrets.token_hex(4)}"
        create_readonly_role(self.engine, role_name, secrets.token_hex(16))
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, "
                        "rolinherit, rolcanlogin, rolreplication FROM pg_roles WHERE rolname = :n"
                    ),
                    {"n": role_name},
                ).one()
            self.assertEqual(
                tuple(row),
                (False, False, False, False, False, True, False),
                "只读角色只能登录，不能有任何提权属性",
            )
        finally:
            drop_readonly_role(self.engine, role_name)


def _four_decimal_fixture(directory) -> "Path":
    """与 `test_database_layer._four_decimal_fixture` 相同：把 A-301 2026 租金规则与对应
    明细改成末位非零的 4 位值（复查 P2-1：原 fixture 末两位是 0，测不出截断）。"""

    import json
    from pathlib import Path

    from app.paths import DEFAULT_FIXTURE_PATH

    data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    for rule in data["lease_charge_rules"]:
        if rule["id"] == "rule_xh_a301_rent_2026":
            rule["unit_price"] = "126.3456"
    for item in data["invoice_items"]:
        if item.get("charge_rule_id") == "rule_xh_a301_rent_2026":
            item["quantity"] = "120.1234"
            item["unit_price"] = "126.3456"
    path = Path(directory) / "four_decimal_fixture.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@requires_pg
class TestFourDecimalReadPathPostgres(unittest.TestCase):
    """复查 P1-1 / P2-1：PG 上 4 位单价 / 数量贯通到仓库输出与应收计算。"""

    def test_statement_matches_fixture_with_nonzero_trailing_digits(self) -> None:
        import tempfile

        _reset_database()
        engine = create_engine_for(PG_URL)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = _four_decimal_fixture(tmp)
                fixture = FixtureRepository.load(path)
                db = build_repository_for_engine(engine, path, create_tables=False)
                expected = fixture.statement(project_ids=SCOPE, lease_id=LEASE)
                actual = db.statement(project_ids=SCOPE, lease_id=LEASE)
                facts = db.lease_facts(project_ids=SCOPE, lease_id=LEASE)
                db._session.close()  # noqa: SLF001 - 测试持有的只读会话
        finally:
            engine.dispose()
            _migrate("downgrade", "base")

        self.assertEqual(actual["rent_variance_total"], expected["rent_variance_total"])
        rent_lines = 0
        for exp_view, act_view in zip(expected["invoices"], actual["invoices"]):
            self.assertEqual(act_view["expected_rent"], exp_view["expected_rent"])
            self.assertEqual(act_view["rent_variance"], exp_view["rent_variance"])
            for exp_item, act_item in zip(exp_view["items"], act_view["items"]):
                self.assertEqual(act_item["quantity"], exp_item["quantity"])
                self.assertEqual(act_item["unit_price"], exp_item["unit_price"])
            if act_view["expected_rent"] is not None:
                rent_lines += 1
                # 120.1234 × 126.3456 = 15177.06；截成 2 位会算出 15177.16
                self.assertEqual(act_view["expected_rent"], Decimal("15177.06"))
        self.assertGreater(rent_lines, 0)
        rule = next(r for r in facts["rules"] if r["id"] == "rule_xh_a301_rent_2026")
        self.assertEqual(rule["unit_price"], "126.3456")


@requires_pg
class TestCliPostgres(_SeededPostgresCase):
    """CLI `--backend postgresql`：只读角色连接、报告元数据、关键数字与 fixture 一致。"""

    role_name: str = ""
    password: str = ""
    role_url: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        import secrets

        from sqlalchemy.engine import make_url

        from app.db.roles import create_readonly_role

        super().setUpClass()
        cls.role_name = f"ro_cli_{secrets.token_hex(4)}"
        cls.password = secrets.token_hex(16)
        create_readonly_role(cls.engine, cls.role_name, cls.password)
        cls.role_url = (
            make_url(PG_URL)
            .set(username=cls.role_name, password=cls.password)
            .render_as_string(hide_password=False)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        from app.db.roles import drop_readonly_role

        try:
            if cls.role_name:
                drop_readonly_role(cls.engine, cls.role_name)
        finally:
            super().tearDownClass()

    def _run_cli(self, argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
        import contextlib
        import io
        from unittest import mock

        from app import cli

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def _env(self) -> dict[str, str]:
        return {
            "COMMERCIAL_DB_URL": self.role_url,
            "DEMO_PRINCIPAL_ID": "principal_ops_xinghui",
        }

    def test_investigate_matches_fixture_and_reports_backend(self) -> None:
        import json

        fixture_code, fixture_out, fixture_err = self._run_cli(
            ["investigate", "--backend", "fixture", "--lease", LEASE], self._env()
        )
        self.assertEqual(fixture_code, 0, fixture_err)
        fixture_payload = json.loads(fixture_out)

        code, out, err = self._run_cli(
            ["investigate", "--backend", "postgresql", "--lease", LEASE], self._env()
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)

        self.assertEqual(payload["verdict"], fixture_payload["verdict"])
        self.assertEqual(payload["backend"], "postgresql")

        def projection(items: list[dict]) -> list[dict]:
            return [
                {
                    "capability": item["capability"],
                    "fund_conclusion": item["fund_conclusion"],
                    "rendered": item["rendered"],
                }
                for item in items
            ]

        self.assertTrue(payload["authoritative_amounts"])
        self.assertEqual(
            projection(payload["authoritative_amounts"]),
            projection(fixture_payload["authoritative_amounts"]),
        )
        self.assertIn("18036.00", out)

        combined = out + err
        self.assertNotIn(self.role_url, combined)
        self.assertNotIn(self.password, combined)
        self.assertNotIn(PG_URL, combined)

    def test_cli_postgres_repository_keeps_dataset_offset(self) -> None:
        """CLI 的 PG engine 必须由 create_engine_for 创建（工单时间带 +08:00）。

        CLI 报告只展示金额/结论，不暴露原始时间字段，因此这里用 CLI 自己的
        装配路径（同一个 `_investigation_assembly`）取出仓库，断言时间偏移；
        若改回 `create_engine`，读出的时间会是 UTC。
        """

        from unittest import mock

        from app import cli

        argv = cli.build_parser().parse_args(
            ["investigate", "--backend", "postgresql", "--lease", LEASE]
        )
        with mock.patch.dict(os.environ, self._env(), clear=False):
            cli._resolve_identity(argv, fallback=cli.DEFAULT_PRINCIPAL_FALLBACK)
            with cli._investigation_assembly(argv) as bundle:
                orders = bundle.repository.work_orders(
                    project_ids=SCOPE, lease_id=LEASE, category="hvac"
                )
        self.assertTrue(orders)
        for order in orders:
            with self.subTest(order=order["id"]):
                self.assertTrue(order["reported_at"].endswith("+08:00"), order["reported_at"])
                if order["resolved_at"] is not None:
                    self.assertTrue(
                        order["resolved_at"].endswith("+08:00"), order["resolved_at"]
                    )

    def test_database_failures_exit_2_without_leaking_connection_info(self) -> None:
        """复查 P3-2：连不上、库未迁移、账号无权限，都退出码 2，且不泄露连接串 / 密码。"""

        import secrets

        from sqlalchemy.engine import make_url

        from app.db.roles import create_readonly_role, drop_readonly_role

        wrong_password = f"wrong_{secrets.token_hex(8)}"
        bad_auth = make_url(self.role_url).set(password=wrong_password).render_as_string(
            hide_password=False
        )
        # 同一服务器上的 `postgres` 库没有迁移过业务表
        unmigrated = make_url(PG_URL).set(database="postgres").render_as_string(
            hide_password=False
        )
        # 一个没有任何表权限的登录角色（建好后收回 SELECT）
        nogrant_role = f"ro_nogrant_{secrets.token_hex(4)}"
        nogrant_password = secrets.token_hex(12)
        create_readonly_role(self.engine, nogrant_role, nogrant_password)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(f'REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM "{nogrant_role}"')
                )
            no_grant = (
                make_url(PG_URL)
                .set(username=nogrant_role, password=nogrant_password)
                .render_as_string(hide_password=False)
            )
            cases = {
                "认证失败": (bad_auth, wrong_password),
                "库未迁移": (unmigrated, make_url(PG_URL).password or ""),
                "无表权限": (no_grant, nogrant_password),
            }
            for label, (url, secret) in cases.items():
                with self.subTest(case=label):
                    code, out, err = self._run_cli(
                        ["investigate", "--backend", "postgresql", "--lease", LEASE],
                        {"COMMERCIAL_DB_URL": url, "DEMO_PRINCIPAL_ID": "principal_ops_xinghui"},
                    )
                    self.assertEqual(code, 2, err)
                    combined = out + err
                    self.assertNotIn(url, combined)
                    if secret:
                        self.assertNotIn(secret, combined)
                    self.assertNotIn("Traceback", combined)
                    self.assertIn("[error]", err)
        finally:
            drop_readonly_role(self.engine, nogrant_role)

    def test_missing_db_url_exits_usage_error(self) -> None:
        code, out, err = self._run_cli(
            ["investigate", "--backend", "postgresql", "--lease", LEASE],
            {"COMMERCIAL_DB_URL": ""},
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("COMMERCIAL_DB_URL", err)

    def test_variant_with_postgres_is_rejected_clearly(self) -> None:
        code, out, err = self._run_cli(
            ["investigate", "--backend", "postgresql", "--variant", "v_oct_rent_corrected"],
            self._env(),
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("postgresql 后端不支持 fixture 数据变体", err)


@requires_pg
class TestConstraintsMigrationDowngradePostgres(unittest.TestCase):
    """0003 的 downgrade 删除全部约束，0002 / 0001 仍能继续降级。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine_for(PG_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        _migrate("downgrade", "base")

    def setUp(self) -> None:
        _reset_database()

    def tearDown(self) -> None:
        _migrate("downgrade", "base")

    def _constraint_names(self) -> set[str]:
        with self.engine.connect() as connection:
            return set(
                connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conname ~ '^(ck|ex)_' AND connamespace = 'public'::regnamespace"
                    )
                ).scalars()
            )

    def test_downgrade_drops_constraints_then_older_revisions(self) -> None:
        expected = set(P0_CONSTRAINT_NAMES) | {EXCLUSION_CONSTRAINT_NAME}
        self.assertEqual(expected - self._constraint_names(), set())

        _migrate("downgrade", "0002")
        self.assertEqual(self._constraint_names(), set())
        # 0002 之后业务表仍在；再降到 0001、base 必须继续成功。
        self.assertIn("leases", _public_tables(self.engine))
        _migrate("downgrade", "0001")
        self.assertIn("leases", _public_tables(self.engine))
        _migrate("downgrade", "base")
        self.assertEqual(_public_tables(self.engine) & set(BUSINESS_TABLES), set())

        # 重新升级后约束必须回来（迁移可重复执行）。
        _migrate("upgrade", "head")
        self.assertEqual(expected - self._constraint_names(), set())


if __name__ == "__main__":
    unittest.main()
