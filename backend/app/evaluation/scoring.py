"""确定性评分（Task 013 / 016）。

评分规则先冻结、再跑保留集，规则版本写进报告（`SCORING_VERSION`）。
本模块只做**可机械复核**的判定，不做语义打分，也不调用模型当裁判。

四类自动断言：

| kind | 判定依据 |
|---|---|
| `facts` | **按字段**比较：`expected_facts[key]` 必须等于基线 `facts[key]`（金额用 `Decimal` 比到分） |
| `evidence` | `required_evidence_ids` 全部出现在证据集合；`forbidden_substrings` 不得出现在答案/事实里 |
| `approval` | 审批状态与草案版本符合预期 |
| `route` | 只命中 `allowed_routes` 与否 → 记为 **efficiency**，不计入 correctness |

`expected_outcome` 决定"被拒绝"是否算对：

- `denied`：基线**必须**以权限/范围拒绝结束，且不得泄露受限数据；拒绝本身不再扣分；
- `ok`：被拒绝或失败一律判失败（与 `denied` 完全对称，避免某条基线因状态命名占便宜）。

`kind="rubric"` 的断言一律 `manual`，不参与自动通过率。

**变更记录（scoring-v2）**：v1 把答案与全部事实拼成一个字符串做子串匹配，
导致"三个金额互换"仍能满分（F1），并对任何 `status=denied` 无条件扣分（F2）。
v2 改为按字段类型化比较，并让拒绝语义由用例显式声明。

**变更记录（scoring-v3，Task 021 / N6）**：v2 只比对内部 `facts`，模型可以
"工具算出未收 18036.00、却回答未收 0.00 已结清"而仍然得分。v3 增加第五类断言

| kind | 判定依据 |
|---|---|
| `answer` | 答案文本中出现的金额必须来自可信事实；出现事实之外的金额即失败，未提及转人工 |

`answer` 断言答的是"用户看到的东西对不对"，`facts` 断言答的是"内部取数对不对"，
两者在汇总里分开统计，不允许用前者代替后者或反之。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ..agents.base.narrative import check_answer_consistency
from .baselines import BaselineResult
from .cases import EvalCase

__all__ = ["CaseScore", "score_case", "SCORING_VERSION", "MONEY_FACT_KEYS"]

#: 评分规则版本。任何判定逻辑变更都必须提升该版本，并新建报告（不覆盖历史）。
SCORING_VERSION = "scoring-v3"

#: 金额类事实键：按 Decimal 比到分（`0.01`）。浮点或字符串近似一律不接受。
MONEY_FACT_KEYS: frozenset[str] = frozenset(
    {
        "invoiced_total",
        "paid_total",
        "valid_paid_total",
        "outstanding_total",
        "oct_rent_billed",
        "oct_rent_should_be",
        "oct_rent_overcharge",
        "draft_amount",
    }
)

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
        "missing_document_ids",
    }
)

#: 基线**实际会产出**的事实键（文档化契约）。用例声明了表内但基线不产出的键时，
#: 判失败但会显式标注"基线未提供该键"，避免把契约缺口误读成实现错误。
BASELINE_FACT_VOCABULARY: frozenset[str] = frozenset(
    {
        "unit_code",
        "lease_id",
        "invoiced_total",
        "paid_total",
        "outstanding_total",
        "work_order_count",
        "open_count",
        "lease_period",
        "lease_status",
        "clause_ref",
        "missing_document_ids",
    }
)


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _compare_fact(key: str, expected: Any, actual: Any) -> tuple[bool | None, str]:
    """按**字段**比较单个期望事实，返回 (是否通过, 说明)。

    金额用 `Decimal` 比到 `0.01`；布尔按真值；列表按集合；其余按去空白后的字符串。
    绝不使用"某个数字在文本里出现过"这种判定。

    返回 `None` 表示**评分器无法自动判定**（该键不在基线事实契约内）：既不算通过也
    不算失败，交人工核对。把"契约里没有这个字段"记成失败，会让开发集这类以自然语言
    断言为主的旧用例集体清零，从而把评分器的能力边界伪装成实现缺陷。
    """

    if key not in BASELINE_FACT_VOCABULARY:
        return None, f"基线事实契约未定义键 {key}（当前值 {actual!r}），转人工核对"
    if actual is None or actual == "":
        return False, f"期望 {key}={expected!r}，基线未提供该字段"

    if isinstance(expected, bool):
        actual_bool = (
            actual if isinstance(actual, bool) else str(actual).strip().lower() == "true"
        )
        return actual_bool == expected, f"期望 {key}={expected}，实际 {actual_bool}"

    if key in MONEY_FACT_KEYS:
        expected_amount = _as_decimal(expected)
        actual_amount = _as_decimal(actual)
        if expected_amount is None or actual_amount is None:
            return False, f"期望 {key}={expected!r} 无法解析为金额，实际 {actual!r}"
        passed = expected_amount.quantize(Decimal("0.01")) == actual_amount.quantize(
            Decimal("0.01")
        )
        return passed, f"期望 {key}={expected_amount}，实际 {actual_amount}"

    if isinstance(expected, (list, tuple, set)):
        expected_set = {str(item).strip() for item in expected}
        if isinstance(actual, (list, tuple, set)):
            actual_set = {str(item).strip() for item in actual}
        else:
            actual_set = {str(actual).strip()}
        passed = expected_set == actual_set
        return passed, f"期望 {key}={sorted(expected_set)}，实际 {sorted(actual_set)}"

    expected_text = str(expected).strip()
    actual_text = str(actual).strip()
    return expected_text == actual_text, f"期望 {key}={expected_text}，实际 {actual_text}"


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
    #: 最终答案与工具事实的一致性结论（N6）：status/trusted/unverified/missing
    answer_check: dict[str, Any] | None = None

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
            "answer_check": self.answer_check,
            "efficiency": self.efficiency,
            "manual_queue": list(self.manual_queue),
            "assertions": [item.as_dict() for item in self.outcomes],
        }


def _haystack(result: BaselineResult) -> str:
    pieces = [result.answer]
    pieces.extend(f"{key}={value}" for key, value in result.facts.items())
    return "\n".join(pieces)


def _declares_content_expectation(case: EvalCase) -> bool:
    """用例是否真的声明了"内容对不对"的断言（而不是只声明路由/结局）。"""

    if case.required_evidence_ids:
        return True
    return any(key in SCORABLE_FACT_KEYS for key in case.expected_facts)


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
        # `passed is None` = 评分器无法自动判定：只进人工队列，不污染分母。
        if kind == "rubric" or passed is None:
            score.manual_queue.append(f"{assertion_id}: {detail}")
            return
        score.correctness_total += 1
        if passed:
            score.correctness_passed += 1

    # 0) 用例声明为人工评定时，只登记到人工队列，不参与自动通过率
    if not case.scorable:
        score.manual_queue.append(
            f"{case.case_id}: 该题声明为人工评定（scorable=false），不参与自动通过率"
        )
        for assertion in case.rubric_assertions:
            score.manual_queue.append(
                f"{assertion.get('id', case.case_id)}: {assertion.get('check', '')}"
            )
        score.efficiency = {
            "route": result.route,
            "allowed_routes": list(case.allowed_routes),
            "route_in_allowed": (
                result.route in case.allowed_routes if case.allowed_routes else None
            ),
            "routed_by": "efficiency_only",
        }
        return score

    # 1) 预期事实：按字段比对，金额用 Decimal
    for key, expected in case.expected_facts.items():
        if key not in SCORABLE_FACT_KEYS:
            score.manual_queue.append(
                f"{case.case_id}: 期望键 {key} 不在评分器可判定范围内，转人工核对"
            )
            continue
        passed, detail = _compare_fact(key, expected, result.facts.get(key))
        record(f"{case.case_id}-F:{key}", "facts", passed, detail)

    # 1b) 最终答案准确性（N6）：用户看到的金额必须来自可信事实。
    # 只有用例本身声明了可判定的内容断言（事实或证据）时才登记——
    # 只用例声明"路由"的题仍必须保持 denominator=0（路由只算效率）。
    if _declares_content_expectation(case):
        answer_check = check_answer_consistency(result.answer, result.facts)
        score.answer_check = answer_check.as_dict()
        if answer_check.status == "mismatch":
            record(f"{case.case_id}-AN", "answer", False, answer_check.detail)
        elif answer_check.status == "not_mentioned":
            record(f"{case.case_id}-AN", "answer", None, answer_check.detail)
        elif answer_check.status == "consistent":
            record(f"{case.case_id}-AN", "answer", True, answer_check.detail)

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

    # 2b) 结局：拒绝/失败是否算对，由用例显式声明（三条基线同一套规则）
    denied = result.status == "denied"
    failed = result.status == "failed"
    if case.expected_outcome == "denied":
        record(
            f"{case.case_id}-O",
            "outcome",
            denied,
            "按预期被拒绝" if denied else f"应被拒绝，实际 status={result.status}",
        )
        if case.expected_error_code:
            matched = any(
                case.expected_error_code in error for error in result.errors
            )
            record(
                f"{case.case_id}-O:code",
                "outcome",
                matched,
                f"期望错误码 {case.expected_error_code}，实际 {result.errors}",
            )
    elif case.expected_outcome == "failed":
        record(
            f"{case.case_id}-O",
            "outcome",
            failed,
            "按预期明确失败" if failed else f"应明确失败，实际 status={result.status}",
        )
    elif denied or failed:
        record(
            f"{case.case_id}-O",
            "outcome",
            False,
            f"基线未给出答案（status={result.status}）: {result.errors}",
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
