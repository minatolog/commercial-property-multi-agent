"""Task 013：数据集、评分规则与三基线评测的自动化验证。

验证边界：
- 只验证**离线**行为（无 `DEEPSEEK_API_KEY`）；报告的模型字段必须标 `offline_deterministic`；
- 评分器是确定性的，因此可以对同一输入断言完全相同的判定结果。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation.baselines import BaselineResult, detect_intents, resolve_lease
from app.evaluation.cases import (
    HELDOUT_CASES,
    SMOKE_CASES,
    EvalCase,
    cases_checksum,
    load_cases,
)
from app.evaluation.scoring import SCORING_VERSION, score_case
from app.fixtures.repository import FixtureRepository


def _case(**overrides) -> EvalCase:
    base = dict(
        case_id="T01",
        title="t",
        user_input="A-301 还欠多少？",
        principal_id="principal_ops_xinghui",
        lease_id="lease_xh_a301_2025",
    )
    base.update(overrides)
    return EvalCase(**base)


def _result(**overrides) -> BaselineResult:
    base = dict(
        baseline="A_deterministic",
        case_id="T01",
        status="ok",
        answer="应收 52596.00、已收 34560.00、未收 18036.00。",
        facts={"outstanding_total": "18036.00"},
        evidence_ids=["inv_2026_10"],
        route="deterministic",
        latency_ms=5,
        tool_calls=1,
    )
    base.update(overrides)
    return BaselineResult(**base)


class TestDatasets(unittest.TestCase):
    def test_dev_split_has_eight_cases(self) -> None:
        self.assertEqual(len(load_cases(split="dev")), 8)

    def test_heldout_split_has_thirty_two_cases(self) -> None:
        cases = load_cases(split="heldout")
        self.assertEqual(len(cases), 32)
        self.assertTrue(all(case.case_id.startswith("H") for case in cases))
        self.assertTrue(all(case.split == "heldout" for case in cases))

    def test_splits_are_separate_files(self) -> None:
        self.assertNotEqual(SMOKE_CASES, HELDOUT_CASES)
        self.assertTrue(HELDOUT_CASES.name.endswith("v3.jsonl"))
        self.assertTrue(HELDOUT_CASES.is_file())

    def test_every_heldout_case_declares_outcome(self) -> None:
        for case in load_cases(split="heldout"):
            self.assertIn(case.expected_outcome, {"ok", "denied", "failed"})

    def test_manual_only_cases_are_declared(self) -> None:
        """人工评定必须在数据里显式声明，而不是"恰好没有断言"。"""

        manual = [case for case in load_cases(split="heldout") if not case.scorable]
        self.assertTrue(manual)
        for case in manual:
            self.assertIn("人工评定", case.notes + str(case.notes))

    def test_checksum_is_stable_and_matches_file(self) -> None:
        first = cases_checksum(HELDOUT_CASES)
        second = cases_checksum(HELDOUT_CASES)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_no_placeholder_expectations(self) -> None:
        """守住 v1 数据集缺陷：期望值里不允许出现 "None"。"""

        for case in load_cases(split="heldout"):
            for key, value in case.expected_facts.items():
                self.assertNotIn(
                    "None", str(value), msg=f"{case.case_id}:{key} 期望值含 None"
                )

    def test_every_case_declares_assertions(self) -> None:
        for case in load_cases(split="heldout"):
            self.assertTrue(case.assertions, msg=f"{case.case_id} 缺少断言声明")

    def test_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.jsonl"
            row = {
                "case_id": "D1",
                "user_input": "q",
                "principal_id": "principal_ops_xinghui",
                "lease_id": "lease_xh_a301_2025",
            }
            path.write_text(
                json.dumps(row, ensure_ascii=False) + "\n" + json.dumps(row, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_cases(path, split="dev")


class TestScoring(unittest.TestCase):
    def test_matching_facts_pass(self) -> None:
        case = _case(expected_facts={"outstanding_total": "18036.00"})
        score = score_case(case, _result())
        self.assertTrue(score.passed)
        self.assertEqual(score.correctness_total, 1)

    def test_approximate_amount_fails(self) -> None:
        case = _case(expected_facts={"outstanding_total": "18036.00"})
        result = _result(answer="大约 1.8 万未收", facts={})
        score = score_case(case, result)
        self.assertFalse(score.passed)

    def test_route_is_efficiency_only(self) -> None:
        case = _case(allowed_routes=("fanout",), expected_facts={})
        result = _result(route="deterministic")
        score = score_case(case, result)
        self.assertEqual(score.correctness_total, 0)
        self.assertIsNone(score.passed)  # 不可评分，而不是失败
        self.assertFalse(score.efficiency["route_in_allowed"])
        self.assertEqual(score.efficiency["routed_by"], "efficiency_only")

    def test_route_hit_does_not_count_as_correctness(self) -> None:
        case = _case(allowed_routes=("deterministic",), expected_facts={})
        score = score_case(case, _result(route="deterministic"))
        self.assertEqual(score.correctness_total, 0)
        self.assertTrue(score.efficiency["route_in_allowed"])

    def test_missing_evidence_fails(self) -> None:
        case = _case(required_evidence_ids=("inv_2026_10", "itm_inv10_rent"))
        score = score_case(case, _result())
        self.assertFalse(score.passed)
        self.assertIn("缺少证据", score.outcomes[0].detail)

    def test_forbidden_substring_fails(self) -> None:
        case = _case(forbidden_substrings=("约 ",))
        score = score_case(case, _result(answer="约 18036.00 元"))
        self.assertFalse(score.passed)

    def test_unsupported_fact_key_goes_to_manual_queue(self) -> None:
        case = _case(expected_facts={"some_unknown_key": "x"})
        score = score_case(case, _result())
        self.assertEqual(score.correctness_total, 0)
        self.assertIsNone(score.passed)
        self.assertFalse(score.applicable)
        self.assertTrue(any("不在评分器可判定范围" in item for item in score.manual_queue))

    def test_contract_gap_does_not_count_as_a_failure(self) -> None:
        """回归：开发集用到的 `verdict` 等键基线不产出，不能把契约缺口记成答错。

        同一题里"可判定断言"与"不可判定断言"混排时，只有前者进分母；
        否则一道只差契约字段的题会被判成 0/N，报告会读成实现全面失败。
        """

        case = _case(
            expected_facts={
                "outstanding_total": "18036.00",
                "verdict": "conflicting",
                "valid_paid_total": "34560.00",
            }
        )
        score = score_case(case, _result(facts={"outstanding_total": "18036.00"}))
        self.assertEqual(score.correctness_total, 1)
        self.assertEqual(score.correctness_passed, 1)
        self.assertTrue(score.passed)
        self.assertEqual(
            len([item for item in score.manual_queue if "契约未定义键" in item]), 2
        )

    def test_rubric_is_not_auto_scored(self) -> None:
        case = _case(
            expected_facts={"outstanding_total": "18036.00"},
            assertions=(
                {"id": "T01-A1", "kind": "facts", "check": "expected_facts"},
                {"id": "T01-R1", "kind": "rubric", "check": "金额表述为确定值"},
            ),
        )
        score = score_case(case, _result())
        self.assertEqual(score.correctness_total, 1)
        self.assertTrue(any("金额表述为确定值" in item for item in score.manual_queue))

    def test_denied_baseline_always_fails_some_assertion(self) -> None:
        case = _case(expected_facts={"outstanding_total": "18036.00"})
        result = _result(status="denied", facts={}, answer="", errors=["permission_denied"])
        score = score_case(case, result)
        self.assertFalse(score.passed)

    def test_scoring_version_is_declared(self) -> None:
        self.assertEqual(SCORING_VERSION, "scoring-v2")


class TestFactFieldBinding(unittest.TestCase):
    """回归 F1：金额必须按字段比较，不能用"文本里出现过"判定。"""

    def _case(self) -> EvalCase:
        return _case(
            expected_facts={
                "invoiced_total": "52596.00",
                "paid_total": "34560.00",
                "outstanding_total": "18036.00",
            }
        )

    def _result(self, facts: dict, *, answer: str = "") -> BaselineResult:
        return _result(facts=facts, answer=answer, evidence_ids=[])

    def test_swapped_amounts_fail(self) -> None:
        score = score_case(
            self._case(),
            self._result(
                {
                    "invoiced_total": "34560.00",
                    "paid_total": "18036.00",
                    "outstanding_total": "52596.00",
                }
            ),
        )
        self.assertFalse(score.passed)
        self.assertEqual(score.correctness_passed, 0)

    def test_correct_numbers_only_in_answer_text_still_fail(self) -> None:
        """答案文本里出现正确金额，但结构化字段为空 → 必须判失败。"""

        score = score_case(
            self._case(),
            self._result(facts={}, answer="应收 52596.00、已收 34560.00、未收 18036.00"),
        )
        self.assertFalse(score.passed)

    def test_substring_of_another_value_does_not_pass(self) -> None:
        """用一个大数字包含正确子串（如 52596.009）不得通过。"""

        score = score_case(
            self._case(),
            self._result(
                {
                    "invoiced_total": "52596.009",
                    "paid_total": "34560.00",
                    "outstanding_total": "18036.00",
                }
            ),
        )
        self.assertFalse(score.passed)
        self.assertEqual(score.correctness_passed, 2)

    def test_money_compared_as_decimal_to_the_cent(self) -> None:
        same = score_case(
            self._case(),
            self._result(
                {
                    "invoiced_total": "52596",
                    "paid_total": "34560.0",
                    "outstanding_total": "18036.00",
                }
            ),
        )
        self.assertTrue(same.passed, "18036 与 18036.00 应视为同一金额")

        off_by_one_cent = score_case(
            self._case(),
            self._result(
                {
                    "invoiced_total": "52596.01",
                    "paid_total": "34560.00",
                    "outstanding_total": "18036.00",
                }
            ),
        )
        self.assertFalse(off_by_one_cent.passed)

    def test_missing_field_reports_explicitly(self) -> None:
        case = _case(expected_facts={"work_order_count": "4"})
        score = score_case(case, _result(facts={"invoiced_total": "1.00"}))
        self.assertFalse(score.passed)
        self.assertIn("基线未提供该字段", score.outcomes[0].detail)

    def test_unknown_vocabulary_key_is_not_scored_either_way(self) -> None:
        """键不在基线事实契约内 → 既不算通过也不算失败，交人工核对。"""

        case = _case(expected_facts={"conflict_detected": True})
        score = score_case(case, _result(facts={"conflict_detected": True}))
        self.assertEqual(score.correctness_total, 0)
        self.assertIsNone(score.passed)
        self.assertIn("基线事实契约未定义键", score.outcomes[0].detail)
        self.assertTrue(
            any("契约未定义键" in item for item in score.manual_queue),
            score.manual_queue,
        )


class TestOutcomeGrading(unittest.TestCase):
    """回归 F2：预期拒绝必须能被正确评分，且三条基线同一套规则。"""

    def test_expected_denial_passes_when_denied_without_leak(self) -> None:
        case = _case(
            expected_outcome="denied",
            expected_error_code="permission_denied",
            forbidden_substrings=("18036.00",),
            expected_facts={},
        )
        score = score_case(
            case,
            _result(
                status="denied",
                facts={},
                answer="",
                errors=["permission_denied: 缺少 billing.read"],
            ),
        )
        self.assertTrue(score.passed, score.as_dict())

    def test_expected_denial_fails_when_baseline_answers(self) -> None:
        case = _case(expected_outcome="denied", expected_facts={})
        score = score_case(case, _result(status="ok", facts={"outstanding_total": "18036.00"}))
        self.assertFalse(score.passed)

    def test_expected_denial_fails_with_wrong_error_code(self) -> None:
        case = _case(
            expected_outcome="denied",
            expected_error_code="project_scope_denied",
            expected_facts={},
        )
        score = score_case(
            case,
            _result(status="denied", facts={}, errors=["permission_denied: 缺少权限"]),
        )
        self.assertFalse(score.passed)

    def test_denial_when_answer_expected_fails(self) -> None:
        case = _case(expected_facts={"outstanding_total": "18036.00"})
        score = score_case(
            case,
            _result(status="denied", facts={}, errors=["permission_denied: 无权限"]),
        )
        self.assertFalse(score.passed)

    def test_expected_failed_outcome(self) -> None:
        case = _case(expected_outcome="failed", expected_facts={})
        self.assertTrue(score_case(case, _result(status="failed", facts={})).passed)
        self.assertFalse(score_case(case, _result(status="ok", facts={})).passed)

    def test_manual_only_case_is_not_scored(self) -> None:
        case = _case(scorable=False, expected_facts={"outstanding_total": "1.00"})
        score = score_case(case, _result(status="ok", facts={}))
        self.assertFalse(score.applicable)
        self.assertIsNone(score.passed)
        self.assertTrue(score.manual_queue)


class TestBaselineHelpers(unittest.TestCase):
    def test_intent_detection_covers_domains(self) -> None:
        self.assertIn("arrears", detect_intents("A-301 还欠多少"))
        self.assertIn("work_orders", detect_intents("A-301 空调报修几条"))
        self.assertIn("clauses", detect_intents("合同里怎么约定的"))
        self.assertEqual(detect_intents("你好"), [])

    def test_lease_resolution_from_unit_code(self) -> None:
        repository = FixtureRepository.load()
        principal = repository.principal("principal_ops_xinghui")
        case = _case(lease_id="", user_input="A-301 的租期是什么时候？")
        self.assertEqual(resolve_lease(repository, principal, case), "lease_xh_a301_2025")

    def test_lease_resolution_denies_other_project(self) -> None:
        repository = FixtureRepository.load()
        principal = repository.principal("principal_ops_xinghui")
        case = _case(lease_id="", user_input="B-101 的租期是什么时候？")
        self.assertEqual(resolve_lease(repository, principal, case), "")


class TestRunnerBindings(unittest.IsolatedAsyncioTestCase):
    async def test_report_binds_versions_and_marks_offline_model(self) -> None:
        from app.evaluation.runner import evaluate

        cases = load_cases(split="heldout")[:2]
        report = await evaluate(baseline="A_deterministic", cases=cases, split="heldout")
        payload = report.as_dict()
        self.assertEqual(payload["bindings"]["scoring_version"], "scoring-v2")
        self.assertEqual(payload["bindings"]["model"]["provider"], "offline_deterministic")
        self.assertEqual(len(payload["bindings"]["cases_sha256"]), 64)
        self.assertIn("code_commit", payload["bindings"])
        summary = payload["summary"]
        self.assertIsNone(summary["cost"]["cost_amount"])
        self.assertEqual(summary["cost"]["cost_basis"], "unavailable_offline_no_pricing")
        self.assertEqual(summary["cost"]["total_tokens"], 0)
        self.assertIn("routing", summary)
        self.assertTrue(summary["routing"]["note"].startswith("仅效率指标"))

    async def test_markdown_mentions_routing_is_efficiency_only(self) -> None:
        from app.evaluation.runner import evaluate, render_markdown

        cases = load_cases(split="heldout")[:1]
        report = await evaluate(baseline="A_deterministic", cases=cases, split="heldout")
        markdown = render_markdown([report])
        self.assertIn("路由命中只作效率指标", markdown)
        self.assertIn("n/a（离线）", markdown)

    async def test_write_report_does_not_overwrite_history(self) -> None:
        from app.evaluation.runner import evaluate, write_report

        cases = load_cases(split="heldout")[:1]
        report = await evaluate(baseline="A_deterministic", cases=cases, split="heldout")
        with tempfile.TemporaryDirectory() as tmp:
            first = write_report(report, out_dir=tmp)
            report.started_at = "2000-01-01T00:00:00+00:00"
            second = write_report(report, out_dir=tmp)
            third = write_report(
                type(report)(**{**report.__dict__, "started_at": "2000-01-01T00:00:01+00:00"}),
                out_dir=tmp,
            )
            self.assertNotEqual(second.name, third.name)
            self.assertTrue(first.is_file())


if __name__ == "__main__":
    unittest.main()
