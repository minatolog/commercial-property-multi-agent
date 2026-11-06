"""模型叙述与工具事实的一致性校验（Task 021 / N6）：用户看到的金额必须可信。

问题背景：`facts` 从工具输出提取，`answer` 由模型自由生成。旧评分只比对 `facts`，
于是出现过这样的组合——工具算出未收 18036.00，模型却回答"未收 0.00，账单已结清"，
评测仍判满分。内部事实正确不等于用户看到的答案正确。

判定规则（纯机械、可复核，不做语义理解）：

- **可信金额集合**：`facts` 中金额类键的取值（与评分器同一份事实契约）
  **加上工具输出里出现过的所有金额**（账单明细、付款、规则金额等）；
- **答案金额**：答案文本中**带两位小数的金额字形**（`18036.00`、`18,036.00`）
  或与某个可信金额完全相等的整数；
- 出现可信集合之外的正则金额 → `mismatch`（用户读到了工具没给过的钱数）；
- 答案写了金额但**一个经核验的合计金额都没写** → `ungrounded`（同样视为问题）；
- 可信金额没出现在答案里 → 记为 `not_mentioned` / `incomplete`（完整性问题，转人工）。

为什么可信集合要包含工具输出的全部金额：模型在答案里列出账单明细（每期租金、物业费、
已核销金额）是正常且可核验的，它们不在 11 键事实契约里，但确实来自工具。只拿 `facts`
判定会把"照实列明细"误报成编造。反过来，只要某个金额**从未出现在任何工具输出里**，
它就是模型自己算或编的，必须被标出来。

边界（必须如实记录，不要当成"已验证"）：

- 只校验金额，不校验叙述里的因果与建议；
- 答案若用"1.8 万"这类改写表达，会被视为未提及该金额；
- 整数形式的金额（`18036`）只有恰好等于可信金额时才被识别为金额，因此
  "合同月租 21600 元"这种整数引用既不会被误判，也不会被核验；
- 模型自己做的四则运算结果（例如"合计应付 3 万元"）不在工具输出里，会被标为不可信。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

__all__ = [
    "AnswerCheck",
    "amounts_in_payload",
    "check_answer_consistency",
    "MONEY_FACT_KEYS",
]

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
#: 整体是一个数字的字符串（工具输出里的金额字段常是字符串）
_NUMERIC_TEXT = re.compile(r"-?\d+(?:\.\d+)?")


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

        return self.status not in {"mismatch", "ungrounded"}

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trusted_amounts": list(self.trusted_amounts),
            "unverified_amounts": list(self.unverified_amounts),
            "missing_amounts": list(self.missing_amounts),
            "detail": self.detail,
        }


def check_answer_consistency(
    answer: str,
    facts: Mapping[str, Any] | None,
    *,
    extra_amounts: Iterable[Any] = (),
) -> AnswerCheck:
    """比对模型叙述里的金额与工具事实。

    `extra_amounts` 是工具输出里出现过的其他金额（账单明细等）。评分器从
    `BaselineResult.verified_amounts` 传入，运行时由 `amounts_in_payload(工具输出)`
    计算——两边用**同一个**可信集合口径。

    判定优先级（越靠前越严重）：

    1. `mismatch`：答案出现**任何工具都没给过**的金额（编造或模型自算）；
    2. `ungrounded`：答案有钱数，但**一个经事实核验的合计金额都没写**
       （"未收 0.00，已经结清"属于这一类——0.00 可能来自某张已结清明细，
       但用户读到的结论没有落到 18036.00 上）；
    3. `not_mentioned`：答案完全没写金额（只说"已核对"），完整性存疑，转人工；
    4. `incomplete`：写了部分事实金额、漏了另一些（可能是只答了被问的那一项）；
    5. `consistent`：事实金额齐全且没有编造金额。
    """

    fact_amounts = _trusted_amounts(facts)
    trusted = set(fact_amounts)
    trusted |= {
        amount
        for amount in (_as_decimal(item) for item in extra_amounts)
        if amount is not None
    }
    if not fact_amounts:
        return AnswerCheck(
            status="not_checkable",
            detail="本次没有可核对的金额事实（例如工单类结论）",
        )

    text = str(answer or "")
    mentioned = _answer_amounts(text, set(trusted))
    unverified = sorted(mentioned - trusted)
    missing = sorted(fact_amounts - mentioned)
    grounded = sorted(fact_amounts & mentioned)

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
    if not mentioned:
        return AnswerCheck(
            status="not_mentioned",
            trusted_amounts=_fmt_all(trusted),
            missing_amounts=_fmt_all(missing),
            detail=("答案未提及任何金额: " + ", ".join(_fmt(item) for item in missing)),
        )
    if not grounded:
        return AnswerCheck(
            status="ungrounded",
            trusted_amounts=_fmt_all(trusted),
            missing_amounts=_fmt_all(missing),
            detail=(
                "答案写了金额但没有一个是经核验的合计金额（应为 "
                + ", ".join(_fmt(item) for item in sorted(fact_amounts))
                + "）"
            ),
        )
    if missing:
        return AnswerCheck(
            status="incomplete",
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


def amounts_in_payload(value: Any, *, _depth: int = 0) -> set[Decimal]:
    """递归收集工具输出里出现过的金额。

    用于把"账单明细/付款/规则金额"这类不在事实契约内、但确实来自工具的数字
    加入可信集合。只认 `Decimal`/`int`/`float` 与**整体为数字的字符串**，
    不在自由文本里猜金额。
    """

    if _depth > 6:
        return set()
    amounts: set[Decimal] = set()
    if isinstance(value, Mapping):
        for item in value.values():
            amounts |= amounts_in_payload(item, _depth=_depth + 1)
        return amounts
    if isinstance(value, (list, tuple, set)):
        for item in value:
            amounts |= amounts_in_payload(item, _depth=_depth + 1)
        return amounts
    if isinstance(value, bool) or value is None:
        return amounts
    if isinstance(value, (int, float, Decimal)):
        amount = _as_decimal(value)
        if amount is not None:
            amounts.add(amount)
        return amounts
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if _NUMERIC_TEXT.fullmatch(text):
            amount = _as_decimal(text)
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
