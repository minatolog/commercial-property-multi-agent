"""资金结论：结构化字段 + 用户可见金额渲染 + 字段级校验（Task 024 / Q3）。

历史缺陷（Task 022 复查 Q3）：叙述核对只判断"答案里的数字是否在可信金额集合中"，
以及"集合里的金额是否都被提到"。于是：

- **反例 A**：应收/已收/未收三个金额互换，数字都在集合里 → `consistent`、满分 4/4；
- **反例 B**：应收正确，但写"未收 0.00，已全部结清" → `0.00` 来自某张明细，
  集合匹配放行，只剩一条"未提及"转人工。

根因是**没有绑定字段**。本模块把资金结论变成结构化对象：

| 层 | 内容 | 由谁决定 |
|---|---|---|
| `FundConclusion` | 应收/已收/未收 + 是否结清 | **只**从工具 facts 赋值，模型无法改写 |
| `render_fund_conclusion` | 用户可见的一句话金额 | 由可信字段渲染，不是模型自由叙述 |
| `FundCheck` | 叙述里的"字段↔金额"是否与结论一致 | 机械解析（标签 + 邻近金额），不做语义判断 |

判定（`FundCheck.status`）：

- `mismatch`：叙述把某个字段写成了别的值，或"已结清/未收 0.00"与未收金额矛盾 → **失败**；
- `verified`：至少绑定了一个字段且全部一致、无矛盾结论 → **通过**；
- `unverified`：叙述没有把任何金额绑定到字段（只说"已核对"或只报了个总数）→
  **未验证**（既不算通过也不算失败，单独统计，绝不冒充"答案准确"）；
- `not_checkable`：本次没有资金事实（例如工单类结论）。

只做机械判定，不做语义理解：不解析因果、建议、免责声明，也不判断"该不该减免"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .narrative import money_tokens

__all__ = [
    "FundConclusion",
    "FundCheck",
    "build_fund_conclusion",
    "check_fund_statements",
    "render_fund_conclusion",
]


#: 字段 → 中文标签。长标签优先匹配（"应收未收"不能被拆成"应收"）。
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "invoiced_total": ("应收未收", "应收合计", "应收", "应缴合计", "应缴", "应收取"),
    "paid_total": ("已收合计", "已收取", "已收", "实收"),
    "outstanding_total": ("未收合计", "未收款", "未收", "尚欠", "欠费", "欠款", "未缴"),
}
#: "应收未收"其实属于未收口径，单独纠正
_LABEL_OVERRIDES: dict[str, str] = {"应收未收": "outstanding_total"}

_SETTLED_PHRASES: tuple[str, ...] = (
    "已结清",
    "全部结清",
    "已经结清",
    "均已结清",
    "结清了",
    "无欠费",
    "没有欠费",
    "无未收",
    "不存在未收",
)

_LABEL_PATTERN = re.compile(
    "|".join(
        re.escape(label)
        for label in sorted(
            {label for labels in _FIELD_LABELS.values() for label in labels},
            key=len,
            reverse=True,
        )
    )
)
#: 标签与金额之间允许的最大字符距离（"应收合计为 52,596.00"这类写法）
_MAX_GAP = 24
#: 金额在前、标签在后时允许的间隔（"52596.00 元应收"）
_MAX_PREFIX_GAP = 8


@dataclass(frozen=True)
class FundConclusion:
    """结构化资金结论：**只**由工具事实赋值。"""

    invoiced_total: str | None = None
    paid_total: str | None = None
    outstanding_total: str | None = None
    currency: str = "CNY"

    @property
    def settled(self) -> bool | None:
        """未收金额为 0 才算结清；缺少未收金额时返回 None（未知，不是"已结清"）。"""

        amount = _as_decimal(self.outstanding_total)
        if amount is None:
            return None
        return amount == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "invoiced_total": self.invoiced_total,
            "paid_total": self.paid_total,
            "outstanding_total": self.outstanding_total,
            "currency": self.currency,
            "settled": self.settled,
        }


@dataclass(frozen=True)
class FundCheck:
    status: str  # verified | mismatch | unverified | not_checkable
    bound_fields: tuple[dict[str, str], ...] = ()
    problems: tuple[str, ...] = ()
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "bound_fields": [dict(item) for item in self.bound_fields],
            "problems": list(self.problems),
            "detail": self.detail,
        }


def build_fund_conclusion(facts: Mapping[str, Any] | None) -> FundConclusion | None:
    """从可信 facts 生成结论；三个字段都没有时返回 None。"""

    data = facts or {}
    invoiced = _text(data.get("invoiced_total"))
    paid = _text(data.get("paid_total"))
    outstanding = _text(data.get("outstanding_total"))
    if invoiced is None and paid is None and outstanding is None:
        return None
    return FundConclusion(
        invoiced_total=invoiced,
        paid_total=paid,
        outstanding_total=outstanding,
    )


def render_fund_conclusion(conclusion: FundConclusion | None) -> str | None:
    """由可信字段渲染用户可见的金额结论（不让模型自己编数字）。"""

    if conclusion is None:
        return None
    parts: list[str] = []
    if conclusion.invoiced_total is not None:
        parts.append(f"应收 {conclusion.invoiced_total}")
    if conclusion.paid_total is not None:
        parts.append(f"已收 {conclusion.paid_total}")
    if conclusion.outstanding_total is not None:
        parts.append(f"未收 {conclusion.outstanding_total}")
        if conclusion.settled:
            parts.append("已结清")
    return f"{'、'.join(parts)}（{conclusion.currency}）" if parts else None


def check_fund_statements(
    answer: str, conclusion: FundConclusion | None
) -> FundCheck:
    """校验叙述里的"字段↔金额"是否与可信结论一致。"""

    if conclusion is None:
        return FundCheck(status="not_checkable", detail="本次没有资金结论可校验")

    trusted = {
        field: _as_decimal(value)
        for field, value in (
            ("invoiced_total", conclusion.invoiced_total),
            ("paid_total", conclusion.paid_total),
            ("outstanding_total", conclusion.outstanding_total),
        )
        if value is not None
    }
    if not trusted:
        return FundCheck(status="not_checkable", detail="本次没有资金结论可校验")

    text = str(answer or "")
    claims, ambiguous = _resolve_bindings(text, set(trusted.values()))
    problems: list[str] = []
    bound_fields: list[dict[str, str]] = []

    for field, amounts in claims.items():
        expected = trusted.get(field)
        if expected is None:
            continue
        for amount in sorted(amounts):
            bound_fields.append(
                {"field": field, "value": _fmt(amount), "expected": _fmt(expected)}
            )
            if amount != expected:
                problems.append(
                    f"字段 {field} 写成了 {_fmt(amount)}，可信值为 {_fmt(expected)}"
                )

    contradiction = _settlement_contradiction(text, conclusion, trusted, claims)
    if contradiction:
        problems.append(contradiction)

    if problems:
        return FundCheck(
            status="mismatch",
            bound_fields=tuple(bound_fields),
            problems=tuple(problems),
            detail="；".join(problems),
        )
    if ambiguous:
        return FundCheck(
            status="unverified",
            bound_fields=tuple(bound_fields),
            problems=tuple(f"字段 {field} 有多个互相矛盾的金额" for field in ambiguous),
            detail=(
                "叙述里同一字段出现多个不同金额，无法判定哪个是结论: "
                + ", ".join(sorted(ambiguous))
            ),
        )
    if not bound_fields:
        return FundCheck(
            status="unverified",
            detail="叙述没有把金额绑定到应收/已收/未收字段，无法核对",
        )
    return FundCheck(
        status="verified",
        bound_fields=tuple(bound_fields),
        detail="字段金额与工具事实一致",
    )


# ---------------------------------------------------------------- 内部

#: 表示"这是合计口径"的词：出现在标签附近时优先作为结论（明细金额不算结论）。
_TOTAL_WORDS: tuple[str, ...] = ("合计", "总计", "共计", "总额", "小计", "累计")
#: 标签前后多大范围内出现合计词才算"合计口径"
_TOTAL_WINDOW = 8


@dataclass(frozen=True)
class _Claim:
    position: int
    amount: Decimal
    strong: bool


def _resolve_bindings(
    text: str, trusted: set[Decimal]
) -> tuple[dict[str, set[Decimal]], set[str]]:
    """把叙述里的字段声明解析成"字段 → 结论金额"。

    真实模型的答案常常既有"合计应收 X"又有逐期明细（"应收租金 15,120.00"）。
    只按"标签后最近的数字"绑定会把明细当成结论，产生误报。因此：

    1. **跳过 Markdown 表格行**（表头/单元格是明细数据，不是结论）；
    2. 同一字段有多个声明时，**优先带合计词的那条**（"合计应收"），否则取第一条；
    3. 优先集里仍有互相矛盾的值 → 记为 ambiguous（未验证），不硬判对错。
    """

    claims: dict[str, list[_Claim]] = {}
    for position, label_start, label_end, field in _label_hits(text):
        amount = _amount_near(text, label_start, label_end, trusted)
        if amount is None:
            continue
        window = text[max(0, label_start - _TOTAL_WINDOW) : label_end + _TOTAL_WINDOW]
        strong = any(word in window for word in _TOTAL_WORDS)
        claims.setdefault(field, []).append(
            _Claim(position=position, amount=amount, strong=strong)
        )

    resolved: dict[str, set[Decimal]] = {}
    ambiguous: set[str] = set()
    for field, items in claims.items():
        strong = [item for item in items if item.strong]
        chosen = strong or [items[0]]
        values = {item.amount for item in chosen}
        if len(values) > 1:
            # 同一字段被写出了多个不同口径的结论：无法判定哪个是"结论"，
            # 既不硬判对错（避免把明细误报成结论），也不冒充已核对。
            ambiguous.add(field)
            continue
        resolved[field] = values
    return resolved, ambiguous


def _label_hits(text: str) -> list[tuple[int, int, int, str]]:
    """返回 (位置, 标签起, 标签止, 字段)；跳过 Markdown 表格行里的标签。"""

    hits: list[tuple[int, int, int, str]] = []
    for match in _LABEL_PATTERN.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if "|" in text[line_start : match.start()]:
            # 表格行里的标签属于明细列，不能当作结论字段
            continue
        hits.append((match.start(), match.start(), match.end(), _field_of(match.group(0))))
    return hits


def _amount_near(
    text: str, label_start: int, label_end: int, trusted: set[Decimal]
) -> Decimal | None:
    tokens = money_tokens(text, trusted=trusted)
    next_label = min(
        (match.start() for match in _LABEL_PATTERN.finditer(text) if match.start() > label_end),
        default=len(text),
    )
    for token_start, _token_end, amount in tokens:
        if token_start < label_end or token_start >= next_label:
            continue
        if token_start - label_end > _MAX_GAP:
            break
        return amount
    # 金额在前："52596.00 元应收"
    previous = [item for item in tokens if item[1] <= label_start]
    if previous:
        _token_start, token_end, amount = previous[-1]
        if label_start - token_end <= _MAX_PREFIX_GAP:
            return amount
    return None


def _settlement_contradiction(
    text: str,
    conclusion: FundConclusion,
    trusted: Mapping[str, Decimal],
    bound: Mapping[str, set[Decimal]],
) -> str | None:
    """"已结清" 与 "未收 != 0" 不能同时成立；反之亦然。"""

    outstanding = trusted.get("outstanding_total")
    if outstanding is None:
        return None
    claims_settled = any(phrase in text for phrase in _SETTLED_PHRASES)
    claims_zero_outstanding = Decimal("0.00") in bound.get("outstanding_total", set())
    if (claims_settled or claims_zero_outstanding) and outstanding != 0:
        return (
            "答案声称已结清/未收 0，但未收金额为 "
            f"{_fmt(outstanding)}，结论与工具事实矛盾"
        )
    if outstanding == 0 and conclusion.settled and bound.get("outstanding_total"):
        wrong = {item for item in bound["outstanding_total"] if item != 0}
        if wrong:
            return (
                "工具事实显示已结清，但答案声称未收 "
                + "、".join(_fmt(item) for item in sorted(wrong))
            )
    return None


def _field_of(label: str) -> str:
    if label in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[label]
    for field, labels in _FIELD_LABELS.items():
        if label in labels:
            return field
    return "unknown"


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).strip().replace(",", "")).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001 - 非金额一律视为不可比
        return None


def _fmt(amount: Decimal) -> str:
    return f"{amount:.2f}"
