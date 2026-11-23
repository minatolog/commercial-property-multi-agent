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
    def setUp(self) -> None:
        # `migrations/env.py` 优先读取 COMMERCIAL_DB_URL；开发者按 README 导出它
        # 再跑全量测试时，这里的 SQLite 迁移会被指向 PG（Task 035 复查 P3 收尾）。
        import os
        from unittest import mock

        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("COMMERCIAL_DB_URL", None)

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


class TestSqliteWithRag(unittest.TestCase):
    """回归 F3：只读数据库后端必须能走完整调查（含合同条款检索）。

    修复前 `build_knowledge_library(repository)` 无条件调用 `snapshot()`，
    而 `DatabaseRepository` 没有该方法，`investigate --backend sqlite` 直接崩溃。
    """

    def test_backend_sqlite_runs_full_investigation_with_clauses(self) -> None:
        import asyncio

        from app.investigation_demo import build_investigation_bundle, run_investigation

        bundle = build_investigation_bundle(backend="sqlite")
        self.assertIsNotNone(bundle.knowledge)
        self.assertIn("document.search", bundle.tool_registry.names())

        result = asyncio.run(
            run_investigation(
                bundle,
                question=(
                    "商铺 A-301 租金金额不一致并要求减免，请核对合同条款、账单与工单。"
                ),
                lease_id=LEASE,
                thread_id="thread_sqlite_rag",
            )
        )

        self.assertEqual(result.verdict, "conflicting")
        self.assertTrue(result.results, "数据库后端应返回子任务结果")

        clause_findings = [
            finding
            for finding in result.report["findings"]
            if finding.get("derivation") == "document_clause"
        ]
        self.assertTrue(clause_findings, "数据库后端也应产出条款证据")
        for finding in clause_findings:
            # F7：证据必须属于本租约（或项目级公共文档）
            self.assertIn(
                finding["source"]["document_id"],
                {"doc_xh_a301_contract", "doc_xh_property_policy"},
            )

    def test_database_repository_exposes_document_catalog(self) -> None:
        _, repository = build_sqlite_repository()
        documents = repository.documents()
        self.assertTrue(documents)
        self.assertEqual(
            {item["id"] for item in documents},
            {
                "doc_xh_a301_contract",
                "doc_xh_property_policy",
                "doc_jl_b101_contract",
            },
        )
        by_id = {item["id"]: item for item in documents}
        # 租约归属必须来自数据，而不是靠文档 ID 猜
        self.assertEqual(
            by_id["doc_xh_a301_contract"]["lease_id"], "lease_xh_a301_2025"
        )
        self.assertIsNone(by_id["doc_xh_property_policy"]["lease_id"])
        self.assertEqual(by_id["doc_jl_b101_contract"]["project_id"], "prj_jinlan")
        for item in documents:
            self.assertIn("project_id", item)


class TestReadOnlyAssembly(unittest.TestCase):
    """回归 S2：装配出来的仓库 Session 必须**真的**是只读的。

    之前 `build_sqlite_repository` 直接用 `Session(engine)`，
    `PRAGMA query_only` 从未执行，"连接层强制只读"只是文档承诺。
    """

    def test_repository_session_rejects_writes(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError

        _, repository = build_sqlite_repository()
        session = repository._session  # noqa: SLF001 - 断言装配结果本身
        self.assertEqual(
            session.execute(text("PRAGMA query_only")).scalar(), 1
        )
        with self.assertRaises(OperationalError):
            session.execute(text("UPDATE invoices SET status = status WHERE 1=0"))

    def test_repository_still_reads_after_gate(self) -> None:
        _, repository = build_sqlite_repository()
        statement = repository.statement(project_ids=SCOPE, lease_id=LEASE)
        self.assertEqual(Decimal(statement["outstanding_total"]), Decimal("18036.00"))


class TestTask035ADataLayerFixesOnSqlite(unittest.TestCase):
    """Task 035A：SQLite 侧对问题 1–4 的追加断言（原有用例保持原样）。"""

    def test_seed_works_with_sqlite_foreign_keys_enforced(self) -> None:
        """问题 1：按父 → 子顺序落库。

        SQLite 默认不检查外键，所以排序错误长期未暴露。这里显式打开
        `PRAGMA foreign_keys = ON` 再 seed，插入顺序本身必须是正确的。
        """

        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import StaticPool

        from app.db.seed import create_schema, seed_from_fixture

        engine = create_engine(
            "sqlite+pysqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
            finally:
                cursor.close()

        create_schema(engine)
        with Session(engine) as session:
            counts = seed_from_fixture(session)
            session.commit()
        with engine.connect() as connection:
            self.assertEqual(
                connection.execute(text("PRAGMA foreign_keys")).scalar_one(), 1
            )
        snapshot = _fixture().snapshot()
        self.assertEqual(counts["buildings"], len(snapshot["buildings"]))
        self.assertEqual(counts["invoice_items"], len(snapshot["invoice_items"]))
        engine.dispose()

    def test_unit_price_and_quantity_keep_four_decimals(self) -> None:
        """问题 4：单价 / 数量保留 4 位小数，金额仍是 2 位。"""

        from sqlalchemy.orm import Session

        from app.db.models import InvoiceItem, LeaseChargeRule

        engine, _ = build_sqlite_repository()
        with Session(engine) as session:
            rule = session.get(LeaseChargeRule, "rule_xh_a301_rent_2027")
            item = session.get(InvoiceItem, "itm_inv10_rent")
        self.assertEqual(str(rule.unit_price), "132.3000")
        self.assertEqual(str(item.quantity), "120.0000")
        self.assertEqual(str(item.unit_price), "132.3000")
        # 金额列保持 `Money`（2 位小数）
        self.assertEqual(str(item.amount), "15876.00")


class TestTask035BConstraintsOnSqlite(unittest.TestCase):
    """Task 035B：迁移 0003 的 P0 约束在 SQLite 上的对应断言（只追加）。

    约束由迁移建立（不是 `create_all`），所以这里在临时文件库上跑完整
    `upgrade head`，再逐类构造违规写入。金额/面积/数量在 SQLite 上是 TEXT，
    迁移使用 `CAST(... AS REAL)`，因此零值与负数都能被正确拒绝。
    """

    @classmethod
    def setUpClass(cls) -> None:
        from sqlalchemy import create_engine

        cls._tmp = tempfile.TemporaryDirectory()
        db_path = Path(cls._tmp.name) / "constraints.sqlite"
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path.as_posix()}")
        command.upgrade(config, "head")
        cls.engine = create_engine(
            f"sqlite+pysqlite:///{db_path.as_posix()}", future=True
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls._tmp.cleanup()

    def _assert_rejected(self, sql: str, constraint: str) -> None:
        from sqlalchemy.exc import IntegrityError

        with self.engine.connect() as connection:
            transaction = connection.begin()
            with self.assertRaises(IntegrityError) as ctx:
                connection.execute(text(sql))
            self.assertIn(constraint, str(ctx.exception))
            transaction.rollback()

    def _assert_accepted(self, sql: str) -> None:
        with self.engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text(sql))
            transaction.rollback()

    def test_migrated_schema_contains_all_p0_constraints(self) -> None:
        expected = {
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
        }
        with self.engine.connect() as connection:
            ddl = "\n".join(
                row[0] or ""
                for row in connection.execute(
                    text("SELECT sql FROM sqlite_master WHERE type = 'table'")
                )
            )
        missing = {name for name in expected if name not in ddl}
        self.assertEqual(missing, set(), f"迁移未创建这些约束: {sorted(missing)}")
        # 排他约束是 PostgreSQL 专属（SQLite 上按设计跳过）。
        self.assertNotIn("ex_leases_unit_active_period_p0", ddl)

    def test_numeric_lower_bounds(self) -> None:
        self._assert_rejected(
            "INSERT INTO payments (id, project_id, receipt_no, payment_method, amount, "
            "currency, paid_at, status) VALUES ('probe_sqlite_pay_neg', 'prj_xinghui', "
            "'PROBE-NEG', 'bank_transfer', '0.00', 'CNY', "
            "'2026-01-01 00:00:00', 'confirmed')",
            "ck_payments_amount_positive_p0",
        )
        self._assert_rejected(
            "INSERT INTO units (id, project_id, building_id, code, area_sqm, "
            "chargeable_area_sqm, physical_status) VALUES ('probe_sqlite_unit', "
            "'prj_xinghui', 'bld_xh_a', 'PROBE-UNIT', '0.00', '10.00', 'normal')",
            "ck_units_area_positive_p0",
        )
        self._assert_rejected(
            "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
            "quantity, unit_price, amount) VALUES ('probe_sqlite_item', 'inv_2026_08', "
            "'rent', 'probe', '1.0000', '1.0000', '-1.00')",
            "ck_invoice_items_amount_adjustment_p0",
        )
        self._assert_rejected(
            "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
            "quantity, unit_price, amount) VALUES ('probe_sqlite_qty', 'inv_2026_08', "
            "'rent', 'probe', '0.0000', '1.0000', '1.00')",
            "ck_invoice_items_quantity_nonzero_p0",
        )
        # 调整类明细（other_fee）允许负数：fixture 没有这种行，但设计允许减免/冲抵。
        self._assert_accepted(
            "INSERT INTO invoice_items (id, invoice_id, charge_type, description, "
            "quantity, unit_price, amount) VALUES ('probe_sqlite_adjust', 'inv_2026_08', "
            "'other_fee', 'probe', '1.0000', NULL, '-1.00')"
        )

    def test_date_ranges_and_enums(self) -> None:
        self._assert_rejected(
            "INSERT INTO leases (id, project_id, lease_no, tenant_id, unit_id, "
            "start_date, end_date, status, billing_cycle, payment_terms_days, "
            "deposit_amount, currency) VALUES ('probe_sqlite_lease', 'prj_xinghui', "
            "'PROBE-DATE', 'ten_xh_yunduan', 'unit_xh_a301', '2026-12-31', "
            "'2026-01-01', 'draft', 'monthly', 30, '0.00', 'CNY')",
            "ck_leases_date_range_p0",
        )
        self._assert_rejected(
            "INSERT INTO leases (id, project_id, lease_no, tenant_id, unit_id, "
            "start_date, end_date, status, billing_cycle, payment_terms_days, "
            "deposit_amount, currency) VALUES ('probe_sqlite_terms', 'prj_xinghui', "
            "'PROBE-TERMS', 'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', "
            "'2026-12-31', 'draft', 'monthly', 181, '0.00', 'CNY')",
            "ck_leases_payment_terms_days_p0",
        )
        self._assert_rejected(
            "INSERT INTO leases (id, project_id, lease_no, tenant_id, unit_id, "
            "start_date, end_date, status, billing_cycle, payment_terms_days, "
            "deposit_amount, currency) VALUES ('probe_sqlite_ccy', 'prj_xinghui', "
            "'PROBE-CCY', 'ten_xh_yunduan', 'unit_xh_a301', '2026-01-01', "
            "'2026-12-31', 'draft', 'monthly', 30, '0.00', 'cny')",
            "ck_leases_currency_format_p0",
        )
        self._assert_rejected(
            "INSERT INTO lease_charge_rules (id, lease_id, charge_type, "
            "calculation_method, unit_price, period_unit, effective_from, "
            "effective_to, is_rent_free) VALUES ('probe_sqlite_rule', "
            "'lease_xh_a301_2025', 'deposit', 'per_sqm', '1.0000', 'month', "
            "'2026-01-01', '2026-12-31', 0)",
            "ck_charge_rules_charge_type_p0",
        )
        self._assert_rejected(
            "INSERT INTO work_orders (id, project_id, work_order_no, category, "
            "priority, status, title, reported_at, resolved_at) VALUES "
            "('probe_sqlite_wo', 'prj_xinghui', 'PROBE-WO', 'hvac', 'normal', "
            "'in_progress', 'probe', '2026-02-02 10:00:00', "
            "'2026-02-01 10:00:00')",
            "ck_work_orders_resolved_after_reported_p0",
        )


def _four_decimal_fixture(directory: Path) -> Path:
    """复制 fixture，把 A-301 2026 年租金规则与对应账单明细改成**末位非零**的 4 位值。

    原 fixture 的 `126.0000` / `120.0000` 末两位是 0：存储或读取时被截成 2 位再补 0，
    与真正保留 4 位在字符串上无法区分（Task 035 复查 P2-1）。
    """

    import json

    from app.paths import DEFAULT_FIXTURE_PATH

    data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    for rule in data["lease_charge_rules"]:
        if rule["id"] == "rule_xh_a301_rent_2026":
            rule["unit_price"] = "126.3456"
    for item in data["invoice_items"]:
        if item.get("charge_rule_id") == "rule_xh_a301_rent_2026":
            item["quantity"] = "120.1234"
            item["unit_price"] = "126.3456"
    path = directory / "four_decimal_fixture.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestFourDecimalReadPath(unittest.TestCase):
    """复查 P1-1 / P2-1：4 位单价 / 数量必须贯通到**仓库输出与应收计算**，不只是 ORM。"""

    def test_statement_and_facts_match_fixture_with_nonzero_trailing_digits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _four_decimal_fixture(Path(tmp))
            fixture = FixtureRepository.load(path)
            engine, db = build_sqlite_repository(path)
            try:
                expected = fixture.statement(project_ids=SCOPE, lease_id=LEASE)
                actual = db.statement(project_ids=SCOPE, lease_id=LEASE)
                facts = db.lease_facts(project_ids=SCOPE, lease_id=LEASE)
            finally:
                engine.dispose()

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
                # 4 位计算：120.1234 × 126.3456 = 15177.06（截成 2 位会算出 120.12 × 126.35 = 15177.16）
                self.assertEqual(act_view["expected_rent"], Decimal("15177.06"))
        self.assertGreater(rent_lines, 0, "至少要有一期租金按 2026 规则计算")
        rule = next(r for r in facts["rules"] if r["id"] == "rule_xh_a301_rent_2026")
        self.assertEqual(rule["unit_price"], "126.3456")


if __name__ == "__main__":
    unittest.main()
