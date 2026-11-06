"""Task 021 / N4、N6：完成条件与"用户看到的答案是否正确"。

N4：模型完全不取证时，图不再判 `supported` / `complete`。
N6：工具事实正确 ≠ 最终回答正确；叙述里的金额必须来自可信事实。

两种反例都在本文件先被复现（回归断言），修复后由同一批断言守住。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Sequence

from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.base.errors import ErrorCode
from app.agents.base.evidence import check_capability_output
from app.agents.base.narrative import check_answer_consistency
from app.agents.factory import build_registry
from app.evaluation.baselines import BaselineResult
from app.evaluation.cases import EvalCase
from app.evaluation.scoring import score_case
from app.fixtures.repository import FixtureRepository
from app.investigation_demo import build_investigation_bundle, run_investigation
from app.llm.model_client import ModelTurn, ModelToolCall
from app.orchestration.investigation import verify_results
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE_A301 = "lease_xh_a301_2025"
CLEARED_ANSWER = "A301 未收金额为 0.00 元，账单已经全部结清。"
CORRECT_ANSWER = "应收 52596.00、已收 34560.00、未收 18036.00。"


class _TextOnlyModel:
    """一个只说话、不调工具的模型（N4 的最小反例）。"""

    provider = "fake"
    model_name = "text-only"

    def __init__(self, text: str = "已经核对，账单没有问题。") -> None:
        self._text = text
        self.calls = 0

    async def complete(self, messages, tools):  # noqa: ANN001
        self.calls += 1
        return ModelTurn(text=self._text, finish_reason="stop")


class _ScriptedModel:
    """按脚本调用指定工具，然后给出固定答案。"""

    provider = "fake"
    model_name = "scripted-tool"

    def __init__(self, tools: Sequence[tuple[str, dict[str, Any]]], answer: str) -> None:
        self._script = list(tools)
        self._answer = answer
        self.calls = 0
        self.invoked: list[str] = []

    async def complete(self, messages, tools):  # noqa: ANN001
        self.calls += 1
        if any(message.tool_calls for message in messages):
            return ModelTurn(text=self._answer, finish_reason="stop")
        exposed = {spec.tool_name: spec.name for spec in tools}
        calls = []
        for tool_name, arguments in self._script:
            name = exposed.get(tool_name)
            if name is None:
                continue
            self.invoked.append(tool_name)
            calls.append(
                ModelToolCall(
                    call_id=f"c{len(calls) + 1}",
                    name=name,
                    arguments=dict(arguments),
                    arguments_json=json.dumps(arguments, ensure_ascii=False),
                )
            )
        if not calls:
            return ModelTurn(text=self._answer, finish_reason="stop")
        return ModelTurn(text="", tool_calls=tuple(calls))


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context(run_id: str = "run_evidence") -> Any:
    trusted = TrustedContext(
        trace_id="trace_evidence",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"lease.read", "billing.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id=run_id)


def _agent(name: str, capability: str, client: Any, *, budget: Budget | None = None):
    report = build_registry(
        tool_registry=_registry(),
        budget=budget or Budget(max_tool_calls=8, max_model_calls=8, max_total_tokens=4000),
        trace_log=TraceLog(),
        engine="llm",
        model_client=client,
    )
    return report.registry.require_capability(capability)


def _run(agent: Any, payload: dict[str, Any], capability: str):
    request = AgentRequest(task_id="t_evidence", capability=capability, payload=payload)
    return asyncio.run(agent.handle(request, _context()))


class TestCapabilityContracts(unittest.TestCase):
    """契约本身：字段缺失即证据不足，0 / 空列表是有效取值。"""

    def test_billing_output_without_facts_is_insufficient(self) -> None:
        self.assertTrue(check_capability_output("billing.statement", {}))
        self.assertTrue(
            check_capability_output(
                "billing.statement", {"lease_id": LEASE_A301, "invoiced_total": "0.00"}
            )
        )

    def test_complete_billing_output_satisfies_contract(self) -> None:
        self.assertEqual(
            check_capability_output(
                "billing.statement",
                {
                    "lease_id": LEASE_A301,
                    "invoiced_total": "0.00",
                    "paid_total": "0.00",
                    "outstanding_total": "0.00",
                },
            ),
            [],
        )

    def test_zero_work_orders_is_a_valid_result(self) -> None:
        self.assertEqual(
            check_capability_output(
                "property.work_orders", {"work_order_count": 0, "open_count": 0}
            ),
            [],
        )

    def test_undeclared_capability_is_not_constrained(self) -> None:
        """允许纯说明的能力不应被硬塞一个取数门槛。"""

        self.assertEqual(check_capability_output("single.investigate", {}), [])

    def test_verify_results_flags_missing_facts(self) -> None:
        verdict, _, missing = verify_results(
            plan=[{"subtask_id": "st_1"}],
            results=[{"subtask_id": "st_1", "capability": "billing.statement", "output": {}}],
            failures=[],
        )
        self.assertEqual(verdict, "insufficient")
        self.assertTrue(any("缺少必需事实" in item for item in missing))


class TestN4ZeroEvidenceIsNotSuccess(unittest.TestCase):
    def test_agent_that_never_calls_a_tool_fails(self) -> None:
        agent = _agent("billing", "billing.statement", _TextOnlyModel())
        result = _run(agent, {"lease_id": LEASE_A301, "question": "A-301 还欠多少"}, "billing.statement")
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(result.output)

    def test_investigation_cannot_be_supported_without_evidence(self) -> None:
        """回归 N4：原来这里是 verdict=supported / completeness=complete。"""

        bundle = build_investigation_bundle(
            engine="llm", model_client=_TextOnlyModel(), max_model_calls=6, max_total_tokens=4000
        )
        result = asyncio.run(
            run_investigation(bundle, question="商铺 A-301 还欠多少钱？", lease_id=LEASE_A301)
        )
        self.assertEqual(result.verdict, "insufficient")
        self.assertEqual(result.report["completeness"], "partial")
        self.assertTrue(result.failures)
        self.assertIn(
            "insufficient_evidence", {item["error_code"] for item in result.failures}
        )
        # 不能凭空产出账单结论
        self.assertEqual(result.report["findings"], [])

    def test_irrelevant_tool_does_not_satisfy_lease_contract(self) -> None:
        """模型想调的工具不在本能力白名单里 → 一次取数都没发生 → 仍然证据不足。"""

        client = _ScriptedModel(
            [("document.search", {"query": "租金递增", "top_k": 2})], answer="合同没有问题。"
        )
        agent = _agent("lease", "lease.query", client)
        result = _run(agent, {"lease_id": LEASE_A301, "question": "租期到什么时候"}, "lease.query")
        self.assertEqual(client.invoked, [], "未注册的工具不应被调用")
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)

    def test_lease_result_without_lease_facts_is_insufficient(self) -> None:
        """有条款命中但没有租约事实，也不能算租约查询完成。"""

        verdict, _, missing = verify_results(
            plan=[{"subtask_id": "st_1"}],
            results=[
                {
                    "subtask_id": "st_1",
                    "capability": "lease.query",
                    "output": {"clauses": [{"clause_id": "5.2"}]},
                }
            ],
            failures=[],
        )
        self.assertEqual(verdict, "insufficient")
        self.assertTrue(any("lease" in item for item in missing))

    def test_all_tools_failing_then_text_is_still_insufficient(self) -> None:
        class _FailingStatement:
            provider = "fake"
            model_name = "failing-tool"

            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, messages, tools):  # noqa: ANN001
                self.calls += 1
                if any(message.tool_calls for message in messages):
                    return ModelTurn(text="账单没有问题，已经全部结清。", finish_reason="stop")
                exposed = {spec.tool_name: spec.name for spec in tools}
                return ModelTurn(
                    text="",
                    tool_calls=(
                        ModelToolCall(
                            call_id="c1",
                            name=exposed["billing.statement.read"],
                            arguments={"lease_id": "lease_not_exist"},
                            arguments_json='{"lease_id": "lease_not_exist"}',
                        ),
                    ),
                )

        agent = _agent("billing", "billing.statement", _FailingStatement())
        result = _run(agent, {"lease_id": LEASE_A301, "question": "欠多少"}, "billing.statement")
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)

    def test_correct_tool_call_still_succeeds(self) -> None:
        """对照组：正常取证必须仍是成功，不能被新契约误伤。"""

        client = _ScriptedModel(
            [("billing.statement.read", {"lease_id": LEASE_A301})], answer=CORRECT_ANSWER
        )
        agent = _agent("billing", "billing.statement", client)
        result = _run(agent, {"lease_id": LEASE_A301, "question": "欠多少"}, "billing.statement")
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual(result.output["facts"]["outstanding_total"], "18036.00")


class TestN6AnswerAccuracy(unittest.TestCase):
    def test_narrative_check_flags_amount_from_nowhere(self) -> None:
        check = check_answer_consistency(CLEARED_ANSWER, {"outstanding_total": "18036.00"})
        self.assertEqual(check.status, "mismatch")
        self.assertIn("0.00", check.unverified_amounts)

    def test_narrative_check_accepts_matching_amounts(self) -> None:
        check = check_answer_consistency(
            CORRECT_ANSWER,
            {
                "invoiced_total": "52596.00",
                "paid_total": "34560.00",
                "outstanding_total": "18036.00",
            },
        )
        self.assertEqual(check.status, "consistent")

    def test_narrative_check_ignores_clause_numbers_and_percentages(self) -> None:
        check = check_answer_consistency(
            "依据合同第 5.2 条，租金递增 20%，未收 18036.00。",
            {"outstanding_total": "18036.00"},
        )
        self.assertEqual(check.status, "consistent")

    def test_narrative_check_without_money_facts_is_not_checkable(self) -> None:
        check = check_answer_consistency("共 4 条工单，1 条未关闭。", {"work_order_count": "4"})
        self.assertEqual(check.status, "not_checkable")

    def test_wrong_narrative_is_visible_and_not_success(self) -> None:
        """回归 N6：工具事实正确、最终回答写了 0.00。"""

        client = _ScriptedModel(
            [("billing.statement.read", {"lease_id": LEASE_A301})], answer=CLEARED_ANSWER
        )
        agent = _agent("billing", "billing.statement", client)
        result = _run(agent, {"lease_id": LEASE_A301, "question": "欠多少"}, "billing.statement")
        self.assertEqual(result.output["facts"]["outstanding_total"], "18036.00")
        self.assertEqual(result.output["answer_check"]["status"], "mismatch")
        self.assertIsNot(result.status, TaskStatus.SUCCESS)
        self.assertTrue(
            any("不一致" in warning for warning in result.warnings), result.warnings
        )

    def test_report_lists_narrative_discrepancies(self) -> None:
        client = _ScriptedModel(
            [("billing.statement.read", {"lease_id": LEASE_A301})], answer=CLEARED_ANSWER
        )
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=client,
            variant="v_oct_rent_corrected",
            max_model_calls=6,
            max_total_tokens=4000,
        )
        result = asyncio.run(
            run_investigation(bundle, question="商铺 A-301 还欠多少钱？", lease_id=LEASE_A301)
        )
        self.assertTrue(result.report["narrative_discrepancies"])
        self.assertTrue(result.report["requires_human_review"])
        self.assertEqual(result.verdict, "supported", "内部事实本身仍是可核验的")

    def test_consistent_narrative_keeps_success(self) -> None:
        client = _ScriptedModel(
            [("billing.statement.read", {"lease_id": LEASE_A301})], answer=CORRECT_ANSWER
        )
        agent = _agent("billing", "billing.statement", client)
        result = _run(agent, {"lease_id": LEASE_A301, "question": "欠多少"}, "billing.statement")
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual(result.output["answer_check"]["status"], "consistent")


class TestN6ScoringSeparatesFactsFromAnswer(unittest.TestCase):
    """回归 N6 的评测侧：facts 全对但答案写错，不能给满分。"""

    def _case(self) -> EvalCase:
        return EvalCase(
            case_id="N6",
            title="答案准确性",
            user_input="A-301 还欠多少？",
            principal_id="principal_ops_xinghui",
            lease_id=LEASE_A301,
            expected_facts={
                "invoiced_total": "52596.00",
                "paid_total": "34560.00",
                "outstanding_total": "18036.00",
            },
        )

    def _result(self, answer: str) -> BaselineResult:
        return BaselineResult(
            baseline="B_single_agent",
            case_id="N6",
            status="ok",
            answer=answer,
            facts={
                "invoiced_total": "52596.00",
                "paid_total": "34560.00",
                "outstanding_total": "18036.00",
            },
        )

    def test_wrong_answer_fails_even_when_facts_are_right(self) -> None:
        score = score_case(self._case(), self._result(CLEARED_ANSWER))
        answer_assertions = [item for item in score.outcomes if item.kind == "answer"]
        self.assertEqual(len(answer_assertions), 1)
        self.assertFalse(answer_assertions[0].passed)
        self.assertFalse(score.passed)
        facts_assertions = [item for item in score.outcomes if item.kind == "facts"]
        self.assertTrue(all(item.passed for item in facts_assertions))

    def test_correct_answer_passes(self) -> None:
        score = score_case(self._case(), self._result(CORRECT_ANSWER))
        self.assertTrue(score.passed)
        self.assertEqual(score.answer_check["status"], "consistent")

    def test_silent_answer_goes_to_manual_not_failure(self) -> None:
        score = score_case(self._case(), self._result("已核对，详见结构化事实。"))
        self.assertEqual(score.answer_check["status"], "not_mentioned")
        self.assertTrue(any("未提及" in item for item in score.manual_queue))
        self.assertTrue(score.passed, "只说'已核对'属于未评，不应等同于写错金额")


if __name__ == "__main__":
    unittest.main()
