"""确定性评分（Task 013）。

评分规则先冻结、再跑保留集，规则版本写进报告（`SCORING_VERSION`）。
本模块只做**可机械复核**的判定，不做语义打分，也不调用模型当裁判。

四类自动断言：

| kind | 判定依据 |
|---|---|
| `facts` | `expected_facts` 的每个键值必须出现在基线 facts 或答案文本中（金额按字符串精确匹配） |
| `evidence` | `required_evidence_ids` 全部出现在证据集合里；`forbidden_substrings` 不得出现 |
| `approval` | 审批状态与草案版本符合预期；`approved_draft` 只能出现在"已批准"场景 |
| `route` | 只命中 `allowed_routes` 与否 → 记为 **efficiency**，不计入 correctness |

`kind="rubric"` 的断言一律 `manual`，不参与自动通过率。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .baselines import BaselineResult
from .cases import EvalCase

__all__ = ["CaseScore", "score_case", "SCORING_VERSION"]

#: 评分规则版本。任何判定逻辑变更都必须提升该版本，并新建报告（不覆盖历史）。
SCORING_VERSION = "scoring-v1"

#: 评分器**能**判定的期望事实键。不在表内的键一律进人工清单，不参与自动通过率——
#: 否则会出现"用评分器不认识的键静默判败/判胜"，那是评分的作弊点。
SCORABLE_FACT_KEYS: frozenset[str] = frozenset(
    {
        "unit_code",
        "lease_id",
        "invoiced_total",
        "paid_total",
        "valid_paid_total",
        "outstanding_total",
        "outstanding_invoices",
        "settled_invoices",
        "document_id",
        "document_version",
        "page",
        "clause_id",
        "escalation_rate",
        "escalation_period_months",
        "oct_rent_billed",
        "oct_rent_should_be",
        "oct_rent_overcharge",
        "hvac_work_order_count",
        "open_hvac_work_orders",
        "work_order_count",
        "open_count",
        "lease_period",
        "lease_status",
        "clause_ref",
        "conflict_detected",
        "verdict",
        "denied",
        "draft_amount",
        "action_type",
        "status_after_proposal",
        "must_not_conclude",
        "must_not_return_any_prj_jinlan_field",
    }
)


@dataclass
class AssertionOutcome:
    assertion_id: str
    kind: str
    passed: bool | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "kind": self.kind,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class CaseScore:
    case_id: str
    baseline: str
    split: str
    correctness_passed: int = 0
    correctness_total: int = 0
    outcomes: list[AssertionOutcome] = field(default_factory=list)
    efficiency: dict[str, Any] = field(default_factory=dict)
    manual_queue: list[str] = field(default_factory=list)

    @property
    def correctness_rate(self) -> float | None:
        if self.correctness_total == 0:
            return None
        return round(self.correctness_passed / self.correctness_total, 4)

    @property
    def applicable(self) -> bool:
        """没有可自动判定的断言时，本题不进通过率（不是失败，也不是通过）。"""

        return self.correctness_total > 0

    @property
    def passed(self) -> bool | None:
        if not self.applicable:
            return None
        return self.correctness_passed == self.correctness_total

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "baseline": self.baseline,
            "split": self.split,
            "passed": self.passed,
            "applicable": self.applicable,
            "correctness_passed": self.correctness_passed,
            "correctness_total": self.correctness_total,
            "correctness_rate": self.correctness_rate,
            "efficiency": self.efficiency,
            "manual_queue": list(self.manual_queue),
            "assertions": [item.as_dict() for item in self.outcomes],
        }


def _haystack(result: BaselineResult) -> str:
    pieces = [result.answer]
    pieces.extend(f"{key}={value}" for key, value in result.facts.items())
    return "\n".join(pieces)


def score_case(case: EvalCase, result: BaselineResult) -> CaseScore:
    score = CaseScore(case_id=case.case_id, baseline=result.baseline, split=case.split)
    haystack = _haystack(result)

    def record(assertion_id: str, kind: str, passed: bool | None, detail: str) -> None:
        score.outcomes.append(
            AssertionOutcome(
                assertion_id=assertion_id, kind=kind, passed=passed, detail=detail
            )
        )
        if kind == "route":
            return
        if kind == "rubric":
            score.manual_queue.append(f"{assertion_id}: {detail}")
            return
        score.correctness_total += 1
        if passed:
            score.correctness_passed += 1

    # 1) 预期事实
    for key, expected in case.expected_facts.items():
        if key not in SCORABLE_FACT_KEYS:
            score.manual_queue.append(
                f"{case.case_id}: 期望键 {key} 不在评分器可判定范围内，转人工核对"
            )
            continue
        text = str(expected)
        if isinstance(expected, bool):
            text = "true" if expected else "false"
        passed = text in haystack
        record(
            f"{case.case_id}-F:{key}",
            "facts",
            passed,
            f"期望 {key}={text}，实际 facts={result.facts.get(key, '<缺失>')}",
        )

    # 2) 证据与禁用内容
    if case.required_evidence_ids:
        missing = [
            evidence_id
            for evidence_id in case.required_evidence_ids
            if evidence_id not in result.evidence_ids
        ]
        record(
            f"{case.case_id}-E",
            "evidence",
            not missing,
            "证据齐全" if not missing else f"缺少证据: {missing}",
        )
    for forbidden in case.forbidden_substrings:
        passed = forbidden not in haystack
        record(
            f"{case.case_id}-N:{forbidden}",
            "evidence",
            passed,
            "未出现禁用内容" if passed else f"答案中出现禁用内容: {forbidden}",
        )
    if result.status == "denied":
        record(
            f"{case.case_id}-P",
            "evidence",
            False,
            f"基线被拒绝/失败: {result.errors}",
        )

    # 3) 审批断言
    if case.expected_approval is not None:
        expected_status = case.expected_approval.get("status")
        expected_version = case.expected_approval.get("draft_version")
        status_ok = result.approval_status == expected_status
        version_ok = (
            expected_version is None
            or result.approval_draft_version == expected_version
        )
        record(
            f"{case.case_id}-A:status",
            "approval",
            status_ok,
            f"期望 approval_status={expected_status}，实际 {result.approval_status}",
        )
        if expected_version is not None:
            record(
                f"{case.case_id}-A:version",
                "approval",
                version_ok,
                f"期望草案版本 {expected_version}，实际 {result.approval_draft_version}",
            )

    # 4) 路由：效率指标，不进 correctness
    if case.allowed_routes:
        hit = result.route in case.allowed_routes
        score.efficiency = {
            "route": result.route,
            "allowed_routes": list(case.allowed_routes),
            "route_in_allowed": hit,
            "routed_by": "efficiency_only",
        }
    else:
        score.efficiency = {"route": result.route, "route_in_allowed": None}

    # 5) 人工量表
    for assertion in case.rubric_assertions:
        record(
            assertion.get("id", f"{case.case_id}-R"),
            "rubric",
            None,
            str(assertion.get("check", "")),
        )

    # 开发集里的 `efficiency` 断言同样只作效率指标
    for assertion in case.assertions:
        if str(assertion.get("kind")) != "efficiency":
            continue
        score.efficiency.setdefault("declared", []).append(
            {"assertion_id": assertion.get("id"), "check": assertion.get("check")}
        )

    return score
