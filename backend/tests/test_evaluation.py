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
        self.assertTrue(HELDOUT_CASES.name.endswith("v2.jsonl"))
        self.assertTrue(HELDOUT_CASES.is_file())

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
        self.assertTrue(any("不在评分器可判定范围" in item for item in score.manual_queue))

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
        self.assertEqual(SCORING_VERSION, "scoring-v1")


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
        self.assertEqual(payload["bindings"]["scoring_version"], "scoring-v1")
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
