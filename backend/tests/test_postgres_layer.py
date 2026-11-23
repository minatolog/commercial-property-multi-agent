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


if __name__ == "__main__":
    unittest.main()
