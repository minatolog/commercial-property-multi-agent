"""Task 024 / Q3：资金结论必须按**字段**核对，金额集合匹配不能证明答案正确。

历史缺陷（Task 022 复查 Q3）：

- 反例 A：应收/已收/未收三个金额互换 → 数字都在可信集合里 → `consistent`、4/4 满分；
- 反例 B：应收正确但写"未收 0.00，已全部结清" → `0.00` 来自明细，集合匹配放行。

本文件固定这些行为：

1. 叙述里的"字段 ↔ 金额"必须等于工具事实（字段写反即失败）；
2. "已结清/未收 0" 与未收金额矛盾即失败；
3. 只答未收、合法明细说明都能通过；
4. 没有把金额绑定到字段时是**未验证**（不算通过，也不算失败）；
5. 内部事实通过与最终答案通过分开统计；
6. 结论由可信字段渲染，不靠模型叙述；测试用数据变体，不硬编码示例金额。
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any, Sequence

from app.agents.base.conclusions import (
    build_fund_conclusion,
    check_fund_statements,
    render_fund_conclusion,
)
from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.single.agent import SingleToolAgent
from app.config.loader import load_agent_config
from app.evaluation.baselines import BaselineResult
from app.evaluation.cases import EvalCase
from app.evaluation.scoring import score_case
from app.fixtures.repository import FixtureRepository
from app.llm.model_client import ModelToolCall, ModelTurn
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE = "lease_xh_a301_2025"

#: 基准变体（v_base）的真实账单事实
BASE_FACTS = {
    "invoiced_total": "52596.00",
    "paid_total": "34560.00",
    "outstanding_total": "18036.00",
}
#: 另一个数据变体（修正后租金）：金额不同，用来证明规则不是按示例硬编码
CORRECTED_FACTS = {
    "invoiced_total": "51840.00",
    "paid_total": "34560.00",
    "outstanding_total": "17280.00",
}


def _swap(facts: dict[str, str]) -> str:
    """把应收/已收/未收三个字段的值写反。"""

    return (
        f"应收 {facts['paid_total']} 元，已收 {facts['outstanding_total']} 元，"
        f"未收 {facts['invoiced_total']} 元。"
    )


class TestFundConclusionRendering(unittest.TestCase):
    """用户可见金额由可信字段渲染，模型叙述不是金额来源。"""

    def test_render_uses_trusted_values(self) -> None:
        conclusion = build_fund_conclusion(BASE_FACTS)
        rendered = render_fund_conclusion(conclusion)
        self.assertIn("52596.00", rendered)
        self.assertIn("34560.00", rendered)
        self.assertIn("18036.00", rendered)
        self.assertNotIn("已结清", rendered)

    def test_settled_flag_comes_from_outstanding(self) -> None:
        settled = build_fund_conclusion({**BASE_FACTS, "outstanding_total": "0.00"})
        self.assertTrue(settled.settled)
        self.assertIn("已结清", render_fund_conclusion(settled))
        self.assertFalse(build_fund_conclusion(BASE_FACTS).settled)

    def test_missing_outstanding_is_unknown_not_settled(self) -> None:
        conclusion = build_fund_conclusion({"invoiced_total": "100.00"})
        self.assertIsNone(conclusion.settled)

    def test_no_fund_facts_means_no_conclusion(self) -> None:
        self.assertIsNone(build_fund_conclusion({"work_order_count": "3"}))


class TestFieldBoundCheck(unittest.TestCase):
    def test_swapped_amounts_are_rejected(self) -> None:
        """回归 Q3 反例 A：三个金额互换。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(_swap(BASE_FACTS), conclusion)
        self.assertEqual(check.status, "mismatch")
        self.assertEqual(len(check.problems), 3)
        self.assertFalse(check.ok)

    def test_swapped_amounts_rejected_on_another_variant(self) -> None:
        """不硬编码示例金额：换一组事实同样能抓到写反。"""

        conclusion = build_fund_conclusion(CORRECTED_FACTS)
        self.assertEqual(
            check_fund_statements(_swap(CORRECTED_FACTS), conclusion).status,
            "mismatch",
        )
        self.assertEqual(
            check_fund_statements(
                f"应收 {CORRECTED_FACTS['invoiced_total']}、已收 "
                f"{CORRECTED_FACTS['paid_total']}、未收 {CORRECTED_FACTS['outstanding_total']}。",
                conclusion,
            ).status,
            "verified",
        )

    def test_wrong_settlement_claim_is_a_contradiction(self) -> None:
        """回归 Q3 反例 B：应收正确，但未收 0 元 + 已全部结清。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "应收 52596.00 元，未收 0.00 元，已经全部结清。", conclusion
        )
        self.assertEqual(check.status, "mismatch")
        self.assertTrue(any("矛盾" in item for item in check.problems))

    def test_settlement_phrase_alone_is_a_contradiction(self) -> None:
        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "应收 52596.00 元，已收 34560.00 元，账单已结清。", conclusion
        )
        self.assertEqual(check.status, "mismatch")

    def test_correct_settlement_on_zero_outstanding_is_verified(self) -> None:
        conclusion = build_fund_conclusion(
            {"invoiced_total": "52596.00", "paid_total": "52596.00", "outstanding_total": "0.00"}
        )
        check = check_fund_statements(
            "应收 52596.00、已收 52596.00、未收 0.00，已结清。", conclusion
        )
        self.assertEqual(check.status, "verified")

    def test_answer_only_outstanding_is_verified(self) -> None:
        """只回答被问的那一项（未收）必须通过。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements("该租约尚欠 18036.00 元。", conclusion)
        self.assertEqual(check.status, "verified")
        self.assertEqual(
            [item["field"] for item in check.bound_fields], ["outstanding_total"]
        )

    def test_legit_itemised_detail_passes(self) -> None:
        """合法明细说明（总账 + 每期金额）必须通过。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "应收合计 52,596.00、已收 34,560.00、未收 18,036.00；"
            "本期租金 17,280.00，物业费 2,160.00。",
            conclusion,
        )
        self.assertEqual(check.status, "verified")

    def test_clause_numbers_and_percentages_are_not_amounts(self) -> None:
        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "依据第 5.2 条（递增 20%），未收 18036.00。", conclusion
        )
        self.assertEqual(check.status, "verified")

    def test_amount_without_field_binding_is_unverified(self) -> None:
        """没有把金额绑定到字段 → 未验证（不是通过）。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements("账单合计 52596.00 元，已核对。", conclusion)
        self.assertEqual(check.status, "unverified")
        self.assertFalse(check.ok)

    def test_markdown_table_rows_are_not_treated_as_conclusions(self) -> None:
        """真实模型会列表格：表头"未收"不能绑到第一行的明细金额上。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "应收 52596.00、已收 34560.00、未收 18036.00。\n\n"
            "| 账单 | 租金 | 未收 |\n|---|---|---|\n| inv_1 | 15,120.00 | 0.00 |\n",
            conclusion,
        )
        self.assertEqual(check.status, "verified")
        self.assertEqual(
            {item["field"] for item in check.bound_fields},
            {"invoiced_total", "paid_total", "outstanding_total"},
        )

    def test_totals_word_takes_precedence_over_detail_amounts(self) -> None:
        """同一字段既有"合计应收"又有逐期"应收租金"时，以合计为准。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "三个月账单合计应收 52,596.00 CNY，已收 34,560.00 CNY，未收 18,036.00 CNY。\n"
            "10 月租金 15,876.00，与账单记录的应收租金 15,120.00 相差 756.00。",
            conclusion,
        )
        self.assertEqual(check.status, "verified")

    def test_conflicting_totals_are_unverified_not_wrong(self) -> None:
        """合计口径本身互相矛盾时判"无法判定"，不硬说对或错。"""

        conclusion = build_fund_conclusion(BASE_FACTS)
        check = check_fund_statements(
            "应收合计 52596.00；另一处又写应收合计 50000.00。", conclusion
        )
        self.assertEqual(check.status, "unverified")
        self.assertIn("invoiced_total", check.detail)

    def test_integer_amounts_bound_to_fields_are_checked(self) -> None:
        conclusion = build_fund_conclusion(BASE_FACTS)
        self.assertEqual(
            check_fund_statements("应收 52596、已收 34560、未收 18036", conclusion).status,
            "verified",
        )
        self.assertEqual(
            check_fund_statements("应收 52596、已收 34560、未收 18000", conclusion).status,
            "mismatch",
        )

    def test_no_money_text_is_unverified(self) -> None:
        conclusion = build_fund_conclusion(BASE_FACTS)
        self.assertEqual(
            check_fund_statements("已核对，详见结构化事实。", conclusion).status,
            "unverified",
        )

    def test_no_fund_facts_is_not_checkable(self) -> None:
        self.assertEqual(
            check_fund_statements("共 3 条工单。", build_fund_conclusion({})).status,
            "not_checkable",
        )


class _ScriptedModel:
    provider = "fake"
    model_name = "scripted-q3"

    def __init__(self, answer: str, lease_id: str | None = LEASE) -> None:
        self._answer = answer
        self._lease_id = lease_id
        self.calls = 0

    async def complete(self, messages: Sequence[Any], tools: Sequence[Any]) -> ModelTurn:
        self.calls += 1
        if any(getattr(message, "tool_calls", ()) for message in messages):
            return ModelTurn(text=self._answer, finish_reason="stop")
        exposed = {spec.tool_name: spec.name for spec in tools}
        args = {"lease_id": self._lease_id} if self._lease_id else {}
        return ModelTurn(
            text="",
            tool_calls=(
                ModelToolCall(
                    call_id="c1",
                    name=exposed["billing.statement.read"],
                    arguments=args,
                    arguments_json='{"lease_id": "x"}',
                ),
            ),
        )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _agent(client: Any) -> SingleToolAgent:
    return SingleToolAgent(
        load_agent_config(CONFIG_DIR / "single.yaml"),
        model_client=client,
        tool_registry=_registry(),
        budget=Budget(max_tool_calls=6, max_model_calls=6, max_total_tokens=4000),
        trace_log=TraceLog(),
    )


def _run(client: Any) -> Any:
    trusted = TrustedContext(
        trace_id="trace_q3",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"billing.read"}),
    )
    return asyncio.run(
        _agent(client).handle(
            AgentRequest(
                task_id="t_q3",
                capability="single.investigate",
                payload={"question": "A-301 还欠多少？", "lease_id": LEASE},
            ),
            trusted.to_agent_context(run_id="run_q3"),
        )
    )


class TestAgentSurfacesFundConclusion(unittest.TestCase):
    def test_wrong_settlement_is_visible_and_not_success(self) -> None:
        result = _run(_ScriptedModel("应收 52596.00 元，未收 0.00 元，已经全部结清。"))
        self.assertIsNot(result.status, TaskStatus.SUCCESS)
        data = result.output
        self.assertEqual(data["fund_check"]["status"], "mismatch")
        self.assertEqual(data["fund_conclusion"]["outstanding_total"], "18036.00")
        # 用户可见金额由可信字段渲染，与模型叙述无关
        self.assertIn("18036.00", data["authoritative_answer"])
        self.assertTrue(any("资金结论" in item for item in result.warnings))

    def test_correct_answer_is_verified(self) -> None:
        result = _run(_ScriptedModel("应收 52596.00、已收 34560.00、未收 18036.00。"))
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual(result.output["fund_check"]["status"], "verified")

    def test_swapped_answer_is_flagged(self) -> None:
        result = _run(
            _ScriptedModel("应收 34560.00、已收 18036.00、未收 52596.00。")
        )
        self.assertEqual(result.output["fund_check"]["status"], "mismatch")
        self.assertNotEqual(result.status, TaskStatus.SUCCESS)


class TestScoringUsesFieldBoundConclusion(unittest.TestCase):
    """评测侧：内部事实通过 ≠ 最终答案通过，且未验证不得计为通过。"""

    def _case(self, facts: dict[str, str]) -> EvalCase:
        return EvalCase(
            case_id="Q3",
            title="资金结论",
            user_input="A-301 还欠多少？",
            principal_id="principal_ops_xinghui",
            lease_id=LEASE,
            expected_facts=dict(facts),
        )

    def _result(self, facts: dict[str, str], answer: str) -> BaselineResult:
        return BaselineResult(
            baseline="B_single_agent",
            case_id="Q3",
            status="ok",
            answer=answer,
            facts=dict(facts),
            verified_amounts=list(facts.values()),
        )

    def test_swapped_amounts_fail_even_though_facts_pass(self) -> None:
        score = score_case(
            self._case(BASE_FACTS), self._result(BASE_FACTS, _swap(BASE_FACTS))
        )
        facts_outcomes = [item for item in score.outcomes if item.kind == "facts"]
        fund_outcomes = [item for item in score.outcomes if item.kind == "fund"]
        self.assertTrue(all(item.passed for item in facts_outcomes))
        self.assertEqual(len(fund_outcomes), 1)
        self.assertFalse(fund_outcomes[0].passed)
        self.assertFalse(score.passed)
        self.assertFalse(score.as_dict()["answer_verified"])

    def test_wrong_settlement_fails(self) -> None:
        score = score_case(
            self._case(BASE_FACTS),
            self._result(BASE_FACTS, "应收 52596.00 元，未收 0.00 元，已经全部结清。"),
        )
        self.assertFalse(score.passed)
        self.assertEqual(score.fund_check["status"], "mismatch")

    def test_unverified_answer_is_not_counted_as_pass(self) -> None:
        score = score_case(
            self._case(BASE_FACTS), self._result(BASE_FACTS, "已核对，详见结构化事实。")
        )
        self.assertEqual(score.fund_check["status"], "unverified")
        self.assertFalse(score.as_dict()["answer_verified"])
        fund = score.as_dict()["fund_check"]
        self.assertEqual(fund["status"], "unverified")
        # 未验证项进人工队列，不冒充通过
        self.assertTrue(any("未绑定" in item or "无法核对" in item for item in score.manual_queue))

    def test_correct_answer_passes_and_is_verified(self) -> None:
        score = score_case(
            self._case(BASE_FACTS),
            self._result(
                BASE_FACTS,
                "应收 52596.00、已收 34560.00、未收 18036.00。",
            ),
        )
        self.assertTrue(score.passed)
        self.assertTrue(score.as_dict()["answer_verified"])

    def test_other_variant_also_works(self) -> None:
        score = score_case(
            self._case(CORRECTED_FACTS),
            self._result(
                CORRECTED_FACTS,
                "应收 51840.00、已收 34560.00、未收 17280.00。",
            ),
        )
        self.assertTrue(score.passed)
        swapped = score_case(
            self._case(CORRECTED_FACTS),
            self._result(CORRECTED_FACTS, _swap(CORRECTED_FACTS)),
        )
        self.assertFalse(swapped.passed)

    def test_report_separates_fact_and_answer_metrics(self) -> None:
        from app.evaluation.runner import _kind_stats, _fund_summary  # noqa: PLC0415

        scores = [
            score_case(
                self._case(BASE_FACTS), self._result(BASE_FACTS, _swap(BASE_FACTS))
            ),
            score_case(
                self._case(BASE_FACTS),
                self._result(
                    BASE_FACTS, "应收 52596.00、已收 34560.00、未收 18036.00。"
                ),
            ),
        ]
        facts = _kind_stats(scores, "facts")
        fund = _kind_stats(scores, "fund")
        summary = _fund_summary(scores)
        self.assertEqual(facts["failed"], 0, "内部事实本身是对的")
        self.assertEqual(fund["failed"], 1, "最终答案写错了")
        self.assertEqual(summary["verified"], 1)
        self.assertEqual(summary["mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
