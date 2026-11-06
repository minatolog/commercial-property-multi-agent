"""Task 010：数据库只读层、迁移与等价性测试。

验证边界（必须如实理解）：

- 本机**没有 PostgreSQL 服务**，因此迁移与查询在 **SQLite** 上验证；
- PostgreSQL 专属能力（原生 `NUMERIC`、`EXCLUDE USING gist`、RLS）**未验证**；
- 金额精确性通过 `Money` 类型在 SQLite 上以 TEXT 存储 + `Decimal` 转换来保证，
  不依赖 SQLite 的 REAL。
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.agents.base.errors import AgentError, ErrorCode
from app.agents.factory import build_registry
from app.db.bootstrap import build_sqlite_repository
from app.db.repository import DatabaseRepository, ReadOnlyViolation
from app.fixtures.repository import FixtureRepository
from app.paths import BACKEND_ROOT
from app.runtime.budget import Budget
from app.runtime.types import TraceLog

SCOPE = frozenset({"prj_xinghui"})
LEASE = "lease_xh_a301_2025"


def _fixture() -> FixtureRepository:
    return FixtureRepository.load()


class TestMigrations(unittest.TestCase):
    def test_upgrade_and_downgrade_on_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "mig.db"
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path.as_posix()}")

            command.upgrade(config, "head")
            self.assertTrue(db_path.exists())

            from sqlalchemy import create_engine

            engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
            with engine.connect() as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                }
            engine.dispose()

            expected = {
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
            }
            self.assertTrue(expected.issubset(tables), expected - tables)

            command.downgrade(config, "base")
            engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
            with engine.connect() as connection:
                remaining = {
                    row[0]
                    for row in connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                }
            engine.dispose()
            self.assertFalse(expected & remaining, expected & remaining)


class TestSeedAndSchema(unittest.TestCase):
    def test_seed_matches_fixture_counts(self) -> None:
        engine, repository = build_sqlite_repository()
        with engine.connect() as connection:
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in (
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
            }
        fixture = _fixture()
        self.assertEqual(counts["units"], len(fixture._data["units"]))
        self.assertEqual(counts["invoices"], len(fixture._data["invoices"]))
        self.assertEqual(counts["payment_allocations"], len(fixture._data["payment_allocations"]))
        self.assertEqual(repository.dataset_version, fixture.dataset_version)


class TestEquivalenceWithFixture(unittest.TestCase):
    """同一输入在 fixture 与数据库上必须返回等价事实。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine, cls.db = build_sqlite_repository()

    def test_arrears_amounts_match(self) -> None:
        fixture = _fixture()
        expected = fixture.arrears(project_ids=SCOPE, lease_id=LEASE)
        actual = self.db.arrears(project_ids=SCOPE, lease_id=LEASE)

        for key in ("invoiced_total", "paid_total", "outstanding_total"):
            self.assertEqual(
                Decimal(str(actual[key])), Decimal(str(expected[key])), key
            )
        self.assertEqual(
            Decimal(str(actual["rent_variance_total"])),
            Decimal("756.00"),
            "数据库侧租金差额",
        )
        self.assertEqual(
            actual["outstanding_invoice_ids"], expected["outstanding_invoice_ids"]
        )

    def test_statement_allocations_and_payments_match(self) -> None:
        fixture = _fixture()
        expected = fixture.statement(project_ids=SCOPE, lease_id=LEASE)
        actual = self.db.statement(project_ids=SCOPE, lease_id=LEASE)

        self.assertEqual(
            {item["id"] for item in actual["allocations"]},
            {item["id"] for item in expected["allocations"]},
        )
        self.assertEqual(
            {item["id"] for item in actual["payments"]},
            {item["id"] for item in expected["payments"]},
        )
        self.assertAlmostEqual(
            float(len(actual["invoices"])), float(len(expected["invoices"]))
        )

    def test_lease_facts_match(self) -> None:
        fixture = _fixture()
        expected = fixture.lease_facts(project_ids=SCOPE, lease_id=LEASE)
        actual = self.db.lease_facts(project_ids=SCOPE, lease_id=LEASE)

        self.assertEqual(actual["lease"]["start_date"], expected["lease"]["start_date"])
        self.assertEqual(actual["lease"]["end_date"], expected["lease"]["end_date"])
        self.assertEqual(actual["lease"]["status"], expected["lease"]["status"])
        self.assertEqual(
            {rule["id"] for rule in actual["rules"]},
            {rule["id"] for rule in expected["rules"]},
        )
        self.assertEqual(actual["missing_documents"], ["doc_xh_a301_annex_b"])
        self.assertEqual(
            actual["missing_documents"], expected["missing_documents"]
        )

    def test_work_orders_match(self) -> None:
        fixture = _fixture()
        expected = fixture.work_orders(project_ids=SCOPE, lease_id=LEASE, category="hvac")
        actual = self.db.work_orders(project_ids=SCOPE, lease_id=LEASE, category="hvac")
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(
            [item["id"] for item in actual], [item["id"] for item in expected]
        )


class TestReadOnlyGuards(unittest.TestCase):
    def test_repository_write_methods_are_rejected(self) -> None:
        _, repository = build_sqlite_repository()
        for method in ("add", "delete", "commit"):
            with self.subTest(method=method):
                with self.assertRaises(ReadOnlyViolation):
                    getattr(repository, method)()

    def test_session_is_query_only(self) -> None:
        """只读闸门确实被打开（PRAGMA query_only = 1）。"""

        from sqlalchemy import text as sql_text

        from app.db.session import session_scope

        engine, _ = build_sqlite_repository()
        with session_scope(engine, read_only=True) as session:
            value = session.execute(sql_text("PRAGMA query_only")).scalar_one()
        self.assertEqual(int(value), 1)

    def test_cross_project_access_is_denied(self) -> None:
        _, repository = build_sqlite_repository()
        with self.assertRaises(AgentError) as ctx:
            repository.arrears(project_ids=SCOPE, lease_id="lease_jl_b101_2025")
        self.assertEqual(ctx.exception.code, ErrorCode.PROJECT_SCOPE_DENIED)

    def test_unknown_lease_is_not_found(self) -> None:
        _, repository = build_sqlite_repository()
        with self.assertRaises(AgentError) as ctx:
            repository.arrears(project_ids=SCOPE, lease_id="lease_does_not_exist")
        self.assertEqual(ctx.exception.code, ErrorCode.RECORD_NOT_FOUND)


class TestReadOnlyDatabaseEnforcement(unittest.TestCase):
    def test_query_only_pragma_blocks_writes(self) -> None:
        """只读闸门在连接层：写语句必须失败，而不是靠"代码里没写"。"""

        from sqlalchemy.orm import Session

        from app.db.session import session_scope

        engine, _ = build_sqlite_repository()
        with session_scope(engine, read_only=True) as session:
            with self.assertRaises(OperationalError):
                session.execute(
                    text(
                        "INSERT INTO projects (id, code, name, timezone, status) "
                        "VALUES ('x', 'X', 'x', 'UTC', 'active')"
                    )
                )


class TestToolsBoundToDatabase(unittest.TestCase):
    def test_investigation_uses_database_repository(self) -> None:
        """工具层不需要修改即可指向数据库仓库（数据源替换的验证）。"""

        from app.agents.base.contracts import AgentContext, AgentRequest
        from app.orchestration.investigation import Investigator
        from app.tools.fixture_tools import build_fixture_tools
        from app.tools.registry import ToolRegistry

        engine, repository = build_sqlite_repository()
        tool_registry = ToolRegistry()
        for tool in build_fixture_tools(repository):
            tool_registry.register(tool)

        budget = Budget(max_tool_calls=12)
        trace_log = TraceLog()
        report = build_registry(
            tool_registry=tool_registry, budget=budget, trace_log=trace_log
        )
        investigator = Investigator(registry=report.registry, repository=repository)
        context = AgentContext(
            trace_id="trace_db",
            run_id="run_db",
            principal_id="principal_ops_xinghui",
            project_ids=SCOPE,
            permissions=frozenset(
                {"lease.read", "billing.read", "property.read", "approval.request"}
            ),
        )
        result = __import__("asyncio").run(
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
        self.assertTrue(any("18036.00" in f["statement"] for f in result.report["findings"]))
        # Task 011：Lease Agent 会额外尝试 document.search。本用例未注册文档工具，
        # 因此必须**降级**（Lease 子任务仍成功 + 明确警告），而不是让调查失败。
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
