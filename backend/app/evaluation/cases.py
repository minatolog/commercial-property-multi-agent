"""评测用例装载与校验（Task 013）。

用例以 JSONL 存放：一行一题，便于 diff 与冻结。开发集与保留集**物理分开**：

| 文件 | 用途 |
|---|---|
| `docs/evaluation/cases/smoke_v1.jsonl` | 8 道开发题（写 Prompt、调工具时可用） |
| `docs/evaluation/cases/heldout_v1.jsonl` | 32 道保留题（冻结后只跑不改） |

保留集的规则：先冻结评分规则（`docs/evaluation/scoring_v1.md`），再由生成脚本产出并记录校验和；
运行后**不得**用保留集结果回头调整 Prompt。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import CASES_DIR

__all__ = [
    "EvalCase",
    "HELDOUT_CASES",
    "SMOKE_CASES",
    "cases_checksum",
    "load_cases",
]

SMOKE_CASES: Path = CASES_DIR / "smoke_v1.jsonl"
#: 保留集当前版本。
#: - v1：生成脚本嵌套取值缺陷（租期为 `None 至 None`），作废存档；
#: - v2：修正期望值；
#: - v3（当前）：新增 `expected_outcome`（拒绝/失败是否算对）与 `scorable` 声明，
#:   并补齐 H22/H27/H30 的机械断言。
#: 历史版本与对应报告全部保留，见 `docs/evaluation/scoring_v2.md`。
HELDOUT_CASES: Path = CASES_DIR / "heldout_v3.jsonl"

_KNOWN_KINDS = frozenset(
    {
        # 保留集（Task 013）
        "facts",
        "evidence",
        "approval",
        "forbidden",
        "route",
        "rubric",
        # Task 016：结局断言（是否按预期被拒绝）
        "outcome",
        # 开发集（Task 006 冻结写法）：programmatic=可机械复核；efficiency=路由效率
        "programmatic",
        "efficiency",
    }
)

#: 开发集里 `programmatic` / `efficiency` 分别映射到的判定类别
_KIND_ALIASES = {"programmatic": "facts", "efficiency": "route"}


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    title: str
    user_input: str
    principal_id: str
    lease_id: str
    variant: str = "v_base"
    dataset_version: str = "agent-first-v1"
    split: str = "dev"
    expected_facts: dict[str, Any] = field(default_factory=dict)
    required_evidence_ids: tuple[str, ...] = ()
    forbidden_substrings: tuple[str, ...] = ()
    allowed_routes: tuple[str, ...] = ()
    expected_approval: dict[str, Any] | None = None
    #: 该题**预期**的结局：`ok`（默认，应给出答案）、`denied`（应被权限/范围拒绝）、
    #: `failed`（应明确失败，例如意图不明）
    expected_outcome: str = "ok"
    #: 预期错误码（`expected_outcome="denied"` 时用于精确核对，可选）
    expected_error_code: str | None = None
    #: `False` 表示该题**声明为人工评定**（离线基线无法机械判定），不计入自动通过率
    scorable: bool = True
    assertions: tuple[dict[str, Any], ...] = ()
    routing_is_efficiency_only: bool = True
    notes: str = ""

    @property
    def rubric_assertions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            item for item in self.assertions if _normalise_kind(item) == "rubric"
        )

    @property
    def automatic_assertions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            item for item in self.assertions if _normalise_kind(item) != "rubric"
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, split: str) -> "EvalCase":
        """兼容两种已有写法：

        - 保留集（本任务新增）：`principal_id` / `lease_id` 直接写在顶层；
        - 开发集（Task 006 冻结）：身份在 `trusted_context.principal_id`，
          租约在 `expected_facts.lease_id`。开发集只读，不改结构。
        """

        if not raw.get("case_id") or not raw.get("user_input"):
            raise ValueError(f"用例缺少 case_id/user_input: {raw.get('case_id', '<unknown>')}")
        outcome = str(raw.get("expected_outcome", "ok"))
        if outcome not in {"ok", "denied", "failed"}:
            raise ValueError(
                f"用例 {raw['case_id']} 的 expected_outcome 非法: {outcome!r}"
                "（可选 ok / denied / failed）"
            )
        trusted = raw.get("trusted_context") or {}
        principal_id = (
            raw.get("principal_id")
            or trusted.get("principal_id")
            or "principal_ops_xinghui"
        )
        expected_facts = dict(raw.get("expected_facts", {}))
        lease_id = str(
            raw.get("lease_id") or expected_facts.get("lease_id") or ""
        )
        for assertion in raw.get("assertions", []):
            if assertion.get("kind") not in _KNOWN_KINDS:
                raise ValueError(
                    f"用例 {raw['case_id']} 含未知断言类型 {assertion.get('kind')!r}"
                )
        return cls(
            case_id=str(raw["case_id"]),
            title=str(raw.get("title", "")),
            user_input=str(raw["user_input"]),
            principal_id=str(principal_id),
            lease_id=lease_id,
            variant=str(raw.get("variant", "v_base")),
            dataset_version=str(raw.get("dataset_version", "agent-first-v1")),
            split=split,
            expected_facts=expected_facts,
            required_evidence_ids=tuple(raw.get("required_evidence_ids", ())),
            forbidden_substrings=tuple(raw.get("forbidden_substrings", ())),
            allowed_routes=tuple(raw.get("allowed_routes", ())),
            expected_approval=raw.get("expected_approval"),
            expected_outcome=str(raw.get("expected_outcome", "ok")),
            expected_error_code=(
                str(raw["expected_error_code"]) if raw.get("expected_error_code") else None
            ),
            scorable=bool(raw.get("scorable", True)),
            assertions=tuple(raw.get("assertions", ())),
            routing_is_efficiency_only=bool(raw.get("routing_is_efficiency_only", True)),
            notes=str(raw.get("notes", "")),
        )


def _normalise_kind(assertion: dict[str, Any]) -> str:
    kind = str(assertion.get("kind", ""))
    return _KIND_ALIASES.get(kind, kind)


def load_cases(path: str | Path | None = None, *, split: str = "dev") -> list[EvalCase]:
    target = Path(path) if path is not None else (
        SMOKE_CASES if split == "dev" else HELDOUT_CASES
    )
    if not target.is_file():
        raise FileNotFoundError(f"用例文件不存在: {target}")
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        raw = json.loads(line)
        case = EvalCase.from_dict(raw, split=split)
        if case.case_id in seen:
            raise ValueError(f"{target.name}:{lineno} 用例 ID 重复: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError(f"{target} 没有任何用例")
    return cases


def cases_checksum(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
