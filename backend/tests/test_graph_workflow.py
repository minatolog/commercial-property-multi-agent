"""Task 009：LangGraph 多 Agent 调查工作流测试。

全部离线：无模型、无数据库、无网络。图与 Agent 均由 fixture + 受控工具驱动。
"""

from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from app.investigation_demo import build_investigation_bundle, run_investigation
from app.orchestration.investigation import RuleBasedPlanner, verify_results
from app.tools.base import BaseTool

C03_QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单，分析争议原因，"
    "指出证据与缺失信息，形成供人工审核的处理方案。"
)
ARREARS_QUESTION = "A-301 现在还有多少钱没交？"
RENT_FREE_QUESTION = "A-301 合同里有没有免租期？"
CROSS_PROJECT_QUESTION = "看一下 B-101 的租金和欠费情况"


class _FlakyTool(BaseTool):
    """第一次超时、之后成功的工具包装（模拟可恢复故障）。

    必须继承 `BaseTool`：工具注册表显式拒绝"看起来像工具"的对象，
    这条约束本身也是安全边界（不允许鸭子类型混入）。
    """

    def __init__(self, inner: BaseTool) -> None:
        self._inner = inner
        self.calls = 0
        self.name = inner.name
        self.version = inner.version
        self.description = inner.description
        self.required_permissions = inner.required_permissions
        self.timeout_seconds = inner.timeout_seconds
        self.max_attempts = 1
        self.input_model = inner.input_model
        self.output_model = inner.output_model

    async def invoke(self, payload: object, context: object):
        from app.agents.base.errors import AgentError, ErrorCode

        self.calls += 1
        if self.calls == 1:
            raise AgentError("第一次调用超时", code=ErrorCode.TOOL_TIMEOUT)
        return await self._inner.invoke(payload, context)


class _AlwaysFailingTool(_FlakyTool):
    async def invoke(self, payload: object, context: object):
        from app.agents.base.errors import AgentError, ErrorCode

        self.calls += 1
        raise AgentError("持续超时", code=ErrorCode.TOOL_TIMEOUT)


class TestPlanner(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = RuleBasedPlanner()

    def test_pure_arrears_question_selects_single_capability(self) -> None:
        subtasks, route = self.planner.plan(ARREARS_QUESTION, {"lease_id": "l1"})
        self.assertEqual(route, "deterministic")
        self.assertEqual(len(subtasks), 1)
        self.assertEqual(subtasks[0]["capability"], "billing.statement")

    def test_complex_question_fans_out_to_three_domains(self) -> None:
        subtasks, route = self.planner.plan(C03_QUESTION, {"lease_id": "l1"})
        self.assertEqual(route, "fanout")
        self.assertEqual(
            {item["capability"] for item in subtasks},
            {"lease.query", "billing.statement", "property.work_orders"},
        )
        self.assertEqual(len({item["subtask_id"] for item in subtasks}), 3)

    def test_hvac_question_passes_category_filter(self) -> None:
        subtasks, _ = self.planner.plan("空调维修了几次？", {"lease_id": "l1"})
        property_task = next(
            item for item in subtasks if item["capability"] == "property.work_orders"
        )
        self.assertEqual(property_task["payload"].get("category"), "hvac")

    def test_unknown_question_defaults_to_billing(self) -> None:
        subtasks, route = self.planner.plan("帮我看看情况", {"lease_id": "l1"})
        self.assertEqual(route, "deterministic")
        self.assertEqual(subtasks[0]["capability"], "billing.statement")


class TestVerifyResults(unittest.TestCase):
    def _result(self, subtask_id: str, **output) -> dict:
        return {
            "subtask_id": subtask_id,
            "capability": output.pop("capability", "billing.statement"),
            "output": output,
        }

    def test_missing_subtask_is_reported(self) -> None:
        verdict, _, missing = verify_results(
            plan=[{"subtask_id": "st_1"}, {"subtask_id": "st_2"}],
            results=[self._result("st_1")],
            failures=[],
        )
        self.assertEqual(verdict, "insufficient")
        self.assertTrue(any("st_2" in item for item in missing))

    def test_conflict_takes_priority_over_missing(self) -> None:
        verdict, conflicts, missing = verify_results(
            plan=[{"subtask_id": "st_1"}, {"subtask_id": "st_2"}],
            results=[
                self._result(
                    "st_1",
                    rent_variance_total="756.00",
                    evidence=[{"evidence_id": "inv_2026_10"}],
                )
            ],
            failures=[],
        )
        self.assertEqual(verdict, "conflicting")
        self.assertEqual(conflicts[0]["amount"], "756.00")
        self.assertTrue(any("st_2" in item for item in missing))

    def test_zero_variance_is_not_conflict(self) -> None:
        verdict, conflicts, _ = verify_results(
            plan=[{"subtask_id": "st_1"}],
            results=[self._result("st_1", rent_variance_total="0.00")],
            failures=[],
        )
        self.assertEqual(verdict, "supported")
        self.assertEqual(conflicts, [])

    def test_failure_marks_insufficient(self) -> None:
        verdict, _, missing = verify_results(
            plan=[{"subtask_id": "st_1"}],
            results=[],
            failures=[{"subtask_id": "st_1", "error_code": "capability_unavailable"}],
        )
        self.assertEqual(verdict, "insufficient")
        self.assertTrue(any("capability_unavailable" in item for item in missing))


class TestInvestigationGraph(unittest.TestCase):
    def test_complex_question_runs_three_subtasks_with_isolated_traces(self) -> None:
        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )

        self.assertEqual(result.route, "fanout")
        self.assertEqual(
            {item["capability"] for item in result.results},
            {"lease.query", "billing.statement", "property.work_orders"},
        )
        self.assertEqual(len({item["subtask_id"] for item in result.results}), 3)
        self.assertEqual(result.failures, ())

        traces = bundle.trace_log.snapshot()
        self.assertEqual(
            {trace.subtask_id for trace in traces},
            {"st_1_lease", "st_2_billing", "st_3_property"},
        )
        # Lease Agent 在 Task 011 起会额外调用 document.search 取条款证据，
        # 因此 Trace 数量按"每个子任务至少一条"断言，而不是固定为 3。
        self.assertGreaterEqual(len(traces), 3)
        self.assertEqual(len({trace.call_id for trace in traces}), len(traces))
        # 同一 run 内所有 Trace 归属一致
        self.assertEqual(len({trace.run_id for trace in traces}), 1)

    def test_conflict_and_missing_document_are_both_reported(self) -> None:
        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        self.assertEqual(result.verdict, "conflicting")
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(Decimal(result.conflicts[0]["amount"]), Decimal("756.00"))
        self.assertTrue(
            any("doc_xh_a301_annex_b" in item for item in result.missing)
        )
        self.assertTrue(result.report["requires_human_review"])

        statements = [item["statement"] for item in result.report["findings"]]
        self.assertTrue(any("18036.00" in text for text in statements))
        self.assertTrue(any("2025-01-01" in text for text in statements))
        self.assertTrue(any("工单 3 条" in text for text in statements))

    def test_simple_question_takes_deterministic_branch(self) -> None:
        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=ARREARS_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        self.assertEqual(result.route, "deterministic")
        self.assertEqual([item["capability"] for item in result.results], ["billing.statement"])
        self.assertEqual(len(bundle.trace_log.snapshot()), 1)

    def test_missing_contract_annex_marks_insufficient(self) -> None:
        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=RENT_FREE_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        self.assertEqual(result.verdict, "insufficient")
        self.assertTrue(any("doc_xh_a301_annex_b" in item for item in result.missing))

    def test_cross_project_request_is_denied_not_answered(self) -> None:
        bundle = build_investigation_bundle(principal_id="principal_ops_xinghui")
        result = asyncio.run(
            run_investigation(
                bundle, question=CROSS_PROJECT_QUESTION, lease_id="lease_jl_b101_2025"
            )
        )
        self.assertEqual(result.verdict, "insufficient")
        self.assertTrue(result.failures)
        self.assertTrue(
            all(
                failure["error_code"] in {"project_scope_denied", "permission_denied"}
                for failure in result.failures
            ),
            result.failures,
        )
        self.assertEqual(result.results, ())

    def test_disabled_capability_degrades_explicitly(self) -> None:
        bundle = build_investigation_bundle()
        bundle.registry.unregister("property")
        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        codes = {failure["error_code"] for failure in result.failures}
        self.assertIn("capability_unavailable", codes)
        # 其余两个能力仍然完成，不能被整体拖垮
        self.assertEqual(len(result.results), 2)
        self.assertTrue(any("st_3_property" in item for item in result.missing))
        # 冲突与不完整是两个维度：既有真实差额，也有未完成的子任务
        self.assertEqual(result.verdict, "conflicting")
        self.assertEqual(result.report["completeness"], "partial")
        self.assertTrue(result.report["requires_human_review"])

    def test_revision_is_bounded(self) -> None:
        bundle = build_investigation_bundle(max_revisions=1)
        bundle.registry.unregister("property")
        asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        # 首轮 1 次 + 补查 1 次 = 最多 2 次；不会无限重试
        property_attempts = [
            trace
            for trace in bundle.trace_log.snapshot()
            if trace.subtask_id == "st_3_property"
        ]
        self.assertEqual(property_attempts, [])

        result = asyncio.run(
            run_investigation(
                build_investigation_bundle(max_revisions=1),
                question=C03_QUESTION,
                lease_id="lease_xh_a301_2025",
            )
        )
        self.assertEqual(result.verdict, "conflicting")

    def test_no_revision_when_failure_is_permanent(self) -> None:
        """文档缺失不应触发补查：重跑也拿不到不存在的文件。"""

        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=RENT_FREE_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        self.assertEqual(result.revision, 0)
        traces = bundle.trace_log.snapshot()
        self.assertEqual({trace.subtask_id for trace in traces}, {"st_1_lease"})

    def test_successful_retry_clears_unresolved_failure(self) -> None:
        """回归 F4：第一次失败、补查成功后，最终状态不得仍判"不完整"。

        修复前 `failures` 是 append 通道且核验把它们当作当前失败，
        补查成功后依然 `insufficient` / `partial`，缺失列表还写着"未获得子任务结果"。

        用 `v_oct_rent_corrected` 变体消除金额差额，让 verdict 走
        `insufficient → 补查` 这条路（有冲突时按设计优先呈现冲突）。
        """

        bundle = build_investigation_bundle(
            variant="v_oct_rent_corrected", max_revisions=1
        )
        flaky = _FlakyTool(bundle.tool_registry.get("property.work_orders.read"))
        bundle.tool_registry.register(flaky, replace=True)

        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )

        self.assertEqual(flaky.calls, 2, "应恰好重试一次")
        self.assertEqual(result.revision, 1)
        self.assertEqual(len(result.results), 3, "补查后三个子任务都应有结果")
        # 当前失败已解决
        self.assertEqual(result.report["failures"], [])
        self.assertEqual(result.failures, ())
        self.assertFalse(
            any("未获得子任务结果" in item for item in result.missing),
            f"缺失列表不应再提未完成子任务: {result.missing}",
        )
        self.assertFalse(
            any("tool_timeout" in item for item in result.missing),
            "已恢复的失败不应留在缺失列表里",
        )
        # 「合同引用但未电子化的文档」是真实资料缺失：verdict 仍为 insufficient，
        # 但这是**文档**缺口，不是补查没跑完（两者必须在报告里可区分）。
        self.assertEqual(result.verdict, "insufficient")
        self.assertEqual(result.report["completeness"], "partial")
        self.assertTrue(
            any("doc_xh_a301_annex_b" in item for item in result.missing)
        )
        # 历史失败仍可审计
        self.assertTrue(result.report["resolved_failures"])

    def test_persistent_failure_stays_insufficient(self) -> None:
        """对照：补查后仍失败时，必须继续报不完整（不能因为重试过就当成功）。"""

        bundle = build_investigation_bundle(
            variant="v_oct_rent_corrected", max_revisions=1
        )
        always_failing = _AlwaysFailingTool(
            bundle.tool_registry.get("property.work_orders.read")
        )
        bundle.tool_registry.register(always_failing, replace=True)

        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        self.assertEqual(always_failing.calls, 2)
        codes = {failure["error_code"] for failure in result.failures}
        self.assertIn("tool_timeout", codes)
        self.assertEqual(result.report["completeness"], "partial")
        self.assertTrue(
            any("未获得子任务结果" in item for item in result.missing)
        )

    def test_report_is_json_serialisable(self) -> None:
        import json

        bundle = build_investigation_bundle()
        result = asyncio.run(
            run_investigation(
                bundle, question=C03_QUESTION, lease_id="lease_xh_a301_2025"
            )
        )
        payload = json.dumps(result.report, ensure_ascii=False, default=str)
        self.assertIn("requires_human_review", payload)
        self.assertNotIn("Traceback", payload)


if __name__ == "__main__":
    unittest.main()
