"""模型叙述与工具事实的一致性校验（Task 021 / N6）：用户看到的金额必须可信。

问题背景：`facts` 从工具输出提取，`answer` 由模型自由生成。旧评分只比对 `facts`，
于是出现过这样的组合——工具算出未收 18036.00，模型却回答"未收 0.00，账单已结清"，
评测仍判满分。内部事实正确不等于用户看到的答案正确。

判定规则（纯机械、可复核，不做语义理解）：

- **可信金额集合**：`facts` 中金额类键的取值（与评分器同一份事实契约）；
- **答案金额**：答案文本中**带两位小数的金额字形**（`18036.00`、`18,036.00`）
  或与某个可信金额完全相等的整数；
- 出现可信集合之外的正则金额 → `mismatch`（用户读到了工具没给过的钱数）；
- 可信金额没出现在答案里 → 记为 `not_mentioned`（是完整性问题，不是错误：回答
  可以只答被问的那一项）。

边界（必须如实记录，不要当成"已验证"）：

- 只校验金额，不校验叙述里的因果与建议；
- 答案若用"1.8 万"这类改写表达，会被视为未提及该金额；
- 整数形式的金额（`18036`）只有恰好等于可信金额时才被识别为金额，因此
  "合同月租 21600 元"这种来自其他工具的整数不会被误判，也不会被核验。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

__all__ = ["AnswerCheck", "check_answer_consistency", "MONEY_FACT_KEYS"]

#: 参与核对的金额事实键（与评分器 `MONEY_FACT_KEYS` 同一口径的超集，
#: 这里只取"会直接展示给用户的资金口径"）。
MONEY_FACT_KEYS: tuple[str, ...] = (
    "invoiced_total",
    "paid_total",
    "valid_paid_total",
    "outstanding_total",
    "oct_rent_billed",
    "oct_rent_should_be",
    "oct_rent_overcharge",
    "draft_amount",
)

#: 两位小数的金额字形；`5.2 条`、`20%`、`2026-11-07` 不会被当成金额。
_MONEY_TOKEN = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d])")
#: 裸整数（只在与可信金额完全相等时才会计入）
_INT_TOKEN = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?![\d.,])")


@dataclass(frozen=True)
class AnswerCheck:
    """一次叙述核对的结论。"""

    status: str  # consistent | mismatch | not_mentioned | not_checkable
    trusted_amounts: tuple[str, ...] = ()
    unverified_amounts: tuple[str, ...] = ()
    missing_amounts: tuple[str, ...] = ()
    detail: str = ""

    @property
    def ok(self) -> bool:
        """是否存在"用户看到了不可信金额"的问题。"""

        return self.status != "mismatch"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trusted_amounts": list(self.trusted_amounts),
            "unverified_amounts": list(self.unverified_amounts),
            "missing_amounts": list(self.missing_amounts),
            "detail": self.detail,
        }


def check_answer_consistency(
    answer: str, facts: Mapping[str, Any] | None
) -> AnswerCheck:
    """比对模型叙述里的金额与工具事实。"""

    trusted = _trusted_amounts(facts)
    if not trusted:
        return AnswerCheck(
            status="not_checkable",
            detail="本次没有可核对的金额事实（例如工单类结论）",
        )

    text = str(answer or "")
    mentioned = _answer_amounts(text, set(trusted))
    unverified = sorted(mentioned - trusted)
    missing = sorted(trusted - mentioned)

    if unverified:
        return AnswerCheck(
            status="mismatch",
            trusted_amounts=_fmt_all(trusted),
            unverified_amounts=_fmt_all(unverified),
            missing_amounts=_fmt_all(missing),
            detail=(
                "答案出现工具事实之外的金额: "
                + ", ".join(_fmt(item) for item in unverified)
            ),
        )
    if missing:
        return AnswerCheck(
            status="not_mentioned",
            trusted_amounts=_fmt_all(trusted),
            missing_amounts=_fmt_all(missing),
            detail=(
                "答案未提及这些金额: "
                + ", ".join(_fmt(item) for item in missing)
            ),
        )
    return AnswerCheck(
        status="consistent",
        trusted_amounts=_fmt_all(trusted),
        detail="答案金额与工具事实一致",
    )


def _trusted_amounts(facts: Mapping[str, Any] | None) -> set[Decimal]:
    amounts: set[Decimal] = set()
    for key in MONEY_FACT_KEYS:
        value = (facts or {}).get(key)
        if value is None or value == "":
            continue
        amount = _as_decimal(value)
        if amount is not None:
            amounts.add(amount)
    return amounts


def _answer_amounts(text: str, trusted: set[Decimal]) -> set[Decimal]:
    amounts: set[Decimal] = set()
    for match in _MONEY_TOKEN.finditer(text):
        amount = _as_decimal(match.group(0))
        if amount is not None:
            amounts.add(amount)
    for match in _INT_TOKEN.finditer(text):
        amount = _as_decimal(match.group(0))
        if amount is not None and amount in trusted:
            amounts.add(amount)
    return amounts


def _as_decimal(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return amount.quantize(Decimal("0.01")) if amount.is_finite() else None


def _fmt(amount: Decimal) -> str:
    return f"{amount:.2f}"


def _fmt_all(amounts: Any) -> tuple[str, ...]:
    return tuple(sorted(_fmt(item) for item in amounts))
