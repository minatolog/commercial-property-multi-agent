"""Task 014：FastAPI 适配层与演示页测试。

验证边界：
- 用 `TestClient` 在进程内调用，不启动真实服务器（无端口占用、无外部依赖）；
- 身份只来自服务端配置；请求自报身份必须被拒；
- 审批走真实的两级串行链路（control_plane + 审批台账），不是假实现。
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.service import RunIndex, WorkflowService
from app.orchestration.checkpointing import checkpoint_config, open_checkpointer

QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单。"
)
LEASE = "lease_xh_a301_2025"


class _ApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.service = WorkflowService(
            index=RunIndex(base / "runs.sqlite"),
            checkpoint_path=base / "graph.sqlite",
            approval_path=base / "approval.sqlite",
        )
        self.client = TestClient(create_app(service=self.service))

    def submit(self, **overrides) -> dict:
        payload = {"question": QUESTION, "lease_id": LEASE}
        payload.update(overrides)
        response = self.client.post("/api/runs", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()


class TestIdentityBoundary(_ApiCase):
    def test_client_cannot_declare_identity(self) -> None:
        for field in ("principal_id", "permissions", "roles"):
            response = self.client.post(
                "/api/runs",
                json={"question": QUESTION, "lease_id": LEASE, field: "principal_finance_jinlan"},
            )
            self.assertEqual(response.status_code, 422, field)
            body = response.json()
            self.assertEqual(body["error"]["code"], "invalid_request")
            self.assertIn(field, body["error"]["message"])

    def test_meta_reports_server_side_principal(self) -> None:
        body = self.client.get("/api/meta").json()
        self.assertEqual(body["trusted_principal"], self.service.principal_id)
        self.assertIn("principal_finance_xinghui", body["approver_allowlist"])

    def test_trace_header_is_present_on_errors(self) -> None:
        response = self.client.get("/api/runs/run_missing")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.headers.get("X-Trace-Id"))
        body = response.json()
        self.assertEqual(body["error"]["code"], "run_not_found")
        self.assertEqual(body["error"]["trace_id"], response.headers["X-Trace-Id"])


class TestInputValidation(_ApiCase):
    """回归 S3：非法参数必须 4xx 且可追踪，不能 500，也不能把 null 当字符串。"""

    def test_invalid_max_tool_calls_rejected(self) -> None:
        for value in ("abc", None, -1, 0, 999):
            response = self.client.post(
                "/api/runs",
                json={"question": QUESTION, "lease_id": LEASE, "max_tool_calls": value},
            )
            self.assertEqual(response.status_code, 422, f"{value!r} -> {response.text}")
            error = response.json()["error"]
            self.assertEqual(error["code"], "invalid_request")
            self.assertTrue(error["trace_id"])
            self.assertTrue(error["details"])

    def test_null_question_is_rejected_not_stringified(self) -> None:
        for value in (None, ""):
            response = self.client.post(
                "/api/runs", json={"question": value, "lease_id": LEASE}
            )
            self.assertEqual(response.status_code, 422, f"{value!r} -> {response.text}")
        # 纯空白由业务层拒绝（也是 4xx，且同样可追踪）
        blank = self.client.post(
            "/api/runs", json={"question": "   ", "lease_id": LEASE}
        )
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["error"]["code"], "invalid_request")

    def test_non_boolean_with_approval_rejected(self) -> None:
        response = self.client.post(
            "/api/runs",
            json={"question": QUESTION, "lease_id": LEASE, "with_approval": "yes"},
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_field_rejected(self) -> None:
        response = self.client.post(
            "/api/runs",
            json={"question": QUESTION, "lease_id": LEASE, "tenant": "x"},
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_approval_payload_rejected(self) -> None:
        created = self.submit()
        version = self.client.get(f"/api/runs/{created['run_id']}").json()["report"][
            "approval_request"
        ]["draft_version"]
        for payload in (
            {"decision": "maybe", "draft_version": version},
            {"decision": "approve", "draft_version": "2"},
            {"decision": "approve", "draft_version": 0},
            {"decision": "approve", "draft_version": version, "principal_id": "x"},
        ):
            response = self.client.post(
                f"/api/runs/{created['run_id']}/approvals",
                json=payload,
                headers={"X-Actor-Id": "principal_property_manager_xinghui"},
            )
            self.assertEqual(response.status_code, 422, f"{payload} -> {response.text}")

    def test_validation_errors_are_traceable(self) -> None:
        response = self.client.post(
            "/api/runs", json={"question": "", "lease_id": LEASE}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["trace_id"], response.headers["X-Trace-Id"]
        )


class TestRunLifecycle(_ApiCase):
    def test_submit_creates_run_awaiting_approval(self) -> None:
        created = self.submit()
        self.assertTrue(created["run_id"].startswith("run_"))
        self.assertEqual(created["status"], "awaiting_approval")
        self.assertEqual(created["approval_status"], "pending_approval")
        self.assertTrue(created["approval_request_id"].startswith("apr_"))

    def test_run_detail_contains_report_evidence_and_budget(self) -> None:
        created = self.submit()
        detail = self.client.get(f"/api/runs/{created['run_id']}").json()
        report = detail["report"]
        self.assertEqual(detail["verdict"], "conflicting")
        self.assertTrue(report["findings"])
        self.assertTrue(report["missing_information"])
        self.assertIn("budget", report)
        self.assertEqual(report["budget"]["used_model_calls"], 0)

    def test_traces_are_isolated_per_run(self) -> None:
        first = self.submit()
        second = self.submit()
        traces_first = self.client.get(f"/api/runs/{first['run_id']}/traces").json()["traces"]
        traces_second = self.client.get(f"/api/runs/{second['run_id']}/traces").json()["traces"]
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertNotEqual(first["thread_id"], second["thread_id"])
        self.assertTrue(traces_first and traces_second)
        self.assertTrue(all(t["subtask_id"] for t in traces_first))
        self.assertNotEqual(
            {t["tool"] for t in traces_first} & {"__none__"}, {"__none__"}
        )

    def test_list_runs_returns_summaries(self) -> None:
        created = self.submit()
        body = self.client.get("/api/runs").json()
        self.assertGreaterEqual(body["count"], 1)
        ids = {item["run_id"] for item in body["runs"]}
        self.assertIn(created["run_id"], ids)
        self.assertNotIn("report", body["runs"][0])


class TestApprovalThroughApi(_ApiCase):
    def test_two_stage_approval_then_approved_draft_only(self) -> None:
        created = self.submit()
        run_id = created["run_id"]
        detail = self.client.get(f"/api/runs/{run_id}").json()
        version = detail["report"]["approval_request"]["draft_version"]

        first = self.client.post(
            f"/api/runs/{run_id}/approvals",
            json={"decision": "approve", "draft_version": version},
            headers={"X-Actor-Id": "principal_property_manager_xinghui"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["approval_status"], "pending_next_stage")
        self.assertIsNone(first.json()["approved_draft"])

        second = self.client.post(
            f"/api/runs/{run_id}/approvals",
            json={"decision": "approve", "draft_version": version},
            headers={"X-Actor-Id": "principal_finance_xinghui"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertEqual(body["approval_status"], "approved")
        self.assertEqual(body["approved_draft"]["status"], "approved_draft_only")
        self.assertEqual(body["approved_draft"]["executed_side_effects"], [])

        detail = self.client.get(f"/api/runs/{run_id}").json()
        self.assertEqual(detail["status"], "completed")

    def test_actor_outside_allowlist_is_rejected(self) -> None:
        """同项目但不在审批人白名单内 → 403（跨项目则被所有权检查挡成 404）。"""

        created = self.submit()
        version = self.client.get(f"/api/runs/{created['run_id']}").json()["report"][
            "approval_request"
        ]["draft_version"]
        response = self.client.post(
            f"/api/runs/{created['run_id']}/approvals",
            json={"decision": "approve", "draft_version": version},
            headers={"X-Actor-Id": "principal_ops_xinghui"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")

    def test_missing_actor_header_is_rejected(self) -> None:
        created = self.submit()
        response = self.client.post(
            f"/api/runs/{created['run_id']}/approvals",
            json={"decision": "approve", "draft_version": 2},
        )
        self.assertEqual(response.status_code, 400)

    def test_stale_draft_version_is_rejected(self) -> None:
        created = self.submit()
        response = self.client.post(
            f"/api/runs/{created['run_id']}/approvals",
            json={"decision": "approve", "draft_version": 1},
            headers={"X-Actor-Id": "principal_property_manager_xinghui"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")


class TestRunIdentity(_ApiCase):
    """回归 S4：公开 run_id、checkpoint context、审批与工具 trace 必须是同一个身份。"""

    def _checkpoint_context_run_id(self, thread_id: str) -> str:
        """直接读回 checkpoint 里的 `InvestigationState.context.run_id`。"""

        async def _read() -> str:
            async with open_checkpointer(self.service.checkpoint_path) as saver:
                snapshot = await saver.aget_tuple(checkpoint_config(thread_id))
            self.assertIsNotNone(snapshot, "运行结束后应留下 checkpoint")
            context = snapshot.checkpoint["channel_values"]["context"]
            return context.run_id

        return asyncio.run(_read())

    def test_public_run_id_matches_traces(self) -> None:
        created = self.submit()
        run_id = created["run_id"]
        traces = self.client.get(f"/api/runs/{run_id}/traces").json()["traces"]
        self.assertTrue(traces)
        self.assertEqual({trace["run_id"] for trace in traces}, {run_id})

    def test_thread_id_is_derived_from_run_id(self) -> None:
        created = self.submit()
        self.assertEqual(created["thread_id"], f"thread_{created['run_id']}")

    def test_checkpoint_context_shares_public_run_id(self) -> None:
        created = self.submit()
        self.assertEqual(
            self._checkpoint_context_run_id(created["thread_id"]), created["run_id"]
        )

    def test_approval_request_belongs_to_same_run(self) -> None:
        created = self.submit()
        detail = self.client.get(f"/api/runs/{created['run_id']}").json()
        request = detail["report"]["approval_request"]
        self.assertEqual(request["run_id"], created["run_id"])
        self.assertEqual(request["thread_id"], created["thread_id"])


class TestRunOwnership(_ApiCase):
    """回归 F8：共用索引/切换主体时不得读到别人的运行。"""

    def test_other_principal_cannot_read_or_list_runs(self) -> None:
        created = self.submit()
        run_id = created["run_id"]

        # 同一份索引，换成另一个项目的主体
        jinlan = WorkflowService(
            principal_id="principal_finance_jinlan",
            index=self.service.index,
            checkpoint_path=self.service.checkpoint_path,
            approval_path=self.service.approval_path,
        )
        jinlan_client = TestClient(create_app(service=jinlan))

        self.assertEqual(
            jinlan_client.get(f"/api/runs/{run_id}").status_code, 404
        )
        self.assertEqual(
            jinlan_client.get(f"/api/runs/{run_id}/traces").status_code, 404
        )
        self.assertEqual(jinlan_client.get("/api/runs").json()["count"], 0)
        self.assertEqual(
            jinlan_client.post(
                f"/api/runs/{run_id}/approvals",
                json={"decision": "approve", "draft_version": 2},
                headers={"X-Actor-Id": "principal_finance_jinlan"},
            ).status_code,
            404,
        )

        # 原主体仍然读得到
        self.assertEqual(self.client.get(f"/api/runs/{run_id}").status_code, 200)

    def test_scope_is_recorded_with_the_run(self) -> None:
        created = self.submit()
        detail = self.client.get(f"/api/runs/{created['run_id']}").json()
        self.assertEqual(detail["project_ids"], ["prj_xinghui"])


class TestPresentationIsOptional(_ApiCase):
    def test_index_page_renders(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("商业地产多 Agent 工作流演示", response.text)
        self.assertIn("/api/runs", response.text)

    def test_cli_and_evaluation_do_not_import_api(self) -> None:
        """删除展示层不应影响 CLI 与评测：它们不能依赖 `app.api`。"""

        import subprocess
        import sys

        project_backend = Path(__file__).resolve().parents[1]
        code = (
            "import sys;"
            "import app.cli, app.evaluation;"
            "assert 'app.api' not in sys.modules, 'CLI/评测不应 import app.api';"
            "print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=project_backend,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
