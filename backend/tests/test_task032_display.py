"""Task 032：只读展示元数据（中文名称 / 引用记录字段）。

约束（交接 Prompt 第 2 节）：只允许新增只读展示元数据；不新增写接口、不改权限语义；
新增字段要有测试。这里守住：
1. 运行详情 `display.lease` 给出租户名、铺位号、楼栋、项目名；列表项带 `display` 摘要；
2. `display.records` 只包含报告实际引用的记录，字段原样搬运（金额是十进制字符串，不计算）；
3. 未电子化文档（只在租约引用与工作备注里出现）给出业务描述，`digitized=false`；
4. 范围外项目的记录一律省略；空范围什么都不返回；
5. `/api/meta.principals` 只含可信主体与审批白名单，且是中文角色名；
6. 没有新增写接口；展示元数据不写入运行记录。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.display import DisplayBuilder, principal_display
from app.api.service import RunIndex, WorkflowService
from app.fixtures.repository import FixtureRepository

QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单。"
)
LEASE = "lease_xh_a301_2025"


class TestRunDisplayMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.service = WorkflowService(
            index=RunIndex(base / "runs.sqlite"),
            checkpoint_path=base / "graph.sqlite",
            approval_path=base / "approval.sqlite",
        )
        cls.client = TestClient(create_app(service=cls.service))
        created = cls.client.post("/api/runs", json={"question": QUESTION, "lease_id": LEASE})
        assert created.status_code == 201, created.text
        cls.run_id = created.json()["run_id"]
        cls.run_view = cls.client.get(f"/api/runs/{cls.run_id}").json()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_lease_display_has_business_names(self) -> None:
        lease = self.run_view["display"]["lease"]
        self.assertEqual(lease["tenant_name"], "云端咖啡（合成租户）")
        self.assertEqual(lease["unit_code"], "A-301")
        self.assertEqual(lease["building_name"], "A座")
        self.assertEqual(lease["project_name"], "星汇广场")
        self.assertEqual(lease["lease_no"], "XH-A301-2025-01")

    def test_list_items_carry_display_summary(self) -> None:
        runs = self.client.get("/api/runs").json()["runs"]
        item = next(run for run in runs if run["run_id"] == self.run_id)
        self.assertEqual(
            item["display"],
            {"tenant_name": "云端咖啡（合成租户）", "unit_code": "A-301", "project_name": "星汇广场"},
        )

    def test_records_are_only_referenced_and_copied_verbatim(self) -> None:
        records = self.run_view["display"]["records"]
        report = self.run_view["report"]
        referenced = set()
        for finding in report["findings"]:
            referenced.update(finding.get("evidence_ids") or ())
        for conflict in report["conflicts"]:
            referenced.update(conflict.get("evidence_ids") or ())
        referenced.update(report["proposed_draft"]["evidence_ids"])
        referenced.update(report["proposed_draft"]["target"].values())
        referenced.add("doc_xh_a301_annex_b")
        self.assertTrue(set(records) <= referenced, set(records) - referenced)
        item = records["itm_inv10_rent"]
        self.assertEqual(item["kind"], "invoice_item")
        self.assertEqual(item["unit_price"], "132.3000")
        self.assertEqual(item["amount"], "15876.00")
        self.assertIsInstance(item["amount"], str, "金额必须保持十进制字符串")
        rule = records["rule_xh_a301_rent_2026"]
        self.assertEqual((rule["kind"], rule["unit_price"]), ("charge_rule", "126.0000"))
        self.assertEqual(records["inv_2026_10"]["period_start"], "2026-10-01")
        self.assertEqual(records["wo_2026_09_25"]["status"], "in_progress")
        # 展示层不产出任何差额/计算字段
        for record in records.values():
            self.assertFalse({"variance", "difference", "computed_variance"} & set(record))

    def test_missing_document_has_business_description(self) -> None:
        annex = self.run_view["display"]["records"]["doc_xh_a301_annex_b"]
        self.assertEqual(annex["kind"], "document")
        self.assertFalse(annex["digitized"])
        self.assertIn("附件B", annex["note"])

    def test_display_is_not_persisted(self) -> None:
        stored = self.service.index.get(self.run_id, project_ids=self.service.project_ids)
        self.assertNotIn("display", stored)

    def test_meta_principals_are_chinese_role_labels(self) -> None:
        meta = self.client.get("/api/meta").json()
        principals = meta["principals"]
        self.assertEqual(set(principals), {meta["trusted_principal"], *meta["approver_allowlist"]})
        self.assertEqual(
            principals["principal_finance_xinghui"]["label"], "星汇广场财务部门审批人（合成）"
        )
        self.assertNotIn("principal_finance_jinlan", principals, "不列出白名单外的主体")

    def test_no_new_write_endpoints(self) -> None:
        app = create_app(service=self.service)
        writes = sorted(
            (route.path, sorted(route.methods - {"HEAD", "OPTIONS"}))
            for route in app.routes
            if getattr(route, "methods", None) and route.methods - {"GET", "HEAD", "OPTIONS"}
        )
        self.assertEqual(
            writes,
            [("/api/runs", ["POST"]), ("/api/runs/{run_id}/approvals", ["POST"])],
        )


class TestDisplayScope(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FixtureRepository.load()

    def test_out_of_scope_records_are_omitted(self) -> None:
        jinlan_only = DisplayBuilder(self.repository, {"prj_jinlan"})
        self.assertIsNone(jinlan_only.lease(LEASE))
        self.assertIsNone(jinlan_only.record("itm_inv10_rent"))
        self.assertIsNone(jinlan_only.record("ten_xh_yunduan"))
        self.assertIsNone(jinlan_only.record("doc_xh_a301_annex_b"))
        self.assertEqual(jinlan_only.lease("lease_jl_b101_2025")["unit_code"], "B-101")

    def test_empty_scope_returns_nothing(self) -> None:
        nothing = DisplayBuilder(self.repository, set())
        self.assertIsNone(nothing.lease(LEASE))
        view = nothing.for_run({"lease_id": LEASE, "report": {"findings": [{"evidence_ids": ["inv_2026_10"]}]}})
        self.assertIsNone(view["lease"])
        self.assertEqual(view["records"], {})

    def test_unknown_ids_and_malformed_report(self) -> None:
        builder = DisplayBuilder(self.repository, {"prj_xinghui"})
        self.assertIsNone(builder.record("nope_123"))
        view = builder.for_run({"lease_id": None, "report": {"findings": "oops", "conflicts": [None, 3]}})
        self.assertIsNone(view["lease"])
        self.assertEqual(view["records"], {})

    def test_principal_display_only_requested(self) -> None:
        labels = principal_display(self.repository, ["principal_ops_xinghui", "ghost"])
        self.assertEqual(list(labels), ["principal_ops_xinghui"])


class TestErrorCodeLabelsInSync(unittest.TestCase):
    """复查 P3-1：后端每个 ErrorCode 在前端都有中文映射，JS 用例里的列表也同步。"""

    STATIC = Path(__file__).resolve().parents[1] / "app" / "api" / "static"

    def _js_keys(self, text: str) -> set[str]:
        import re

        block = re.search(r"errorCode:\s*\{(.*?)\n\s*\},", text, re.S)
        self.assertIsNotNone(block, "i18n.js 中找不到 errorCode 映射")
        return set(re.findall(r"^\s*([a-z_]+):\s*'", block.group(1), re.M))

    def test_every_backend_error_code_has_label(self) -> None:
        import re

        from app.agents.base.errors import ErrorCode

        backend = {code.value for code in ErrorCode}
        i18n = (self.STATIC / "js" / "i18n.js").read_text(encoding="utf-8")
        self.assertEqual(backend - self._js_keys(i18n), set(), "以下错误码缺少中文映射")

        cases = (self.STATIC / "tests" / "ui-model-cases.js").read_text(encoding="utf-8")
        listed = re.search(r"BACKEND_ERROR_CODES = \[(.*?)\];", cases, re.S)
        self.assertIsNotNone(listed)
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", listed.group(1))), backend)


if __name__ == "__main__":
    unittest.main()
