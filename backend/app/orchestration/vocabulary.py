"""领域词表：确定性路由的**唯一词表来源**（Task 031 / 2.7）。

为什么把它单独成模块：

- `RuleBasedPlanner` 用它决定"问题落在哪个领域"；
- `ask` 路径的目标识别也 import 同一份词表，两处口径必须一致；
- 词表是**业务语义**而不是实现细节，每个词都必须能追溯到来源
  （见 [planner_vocabulary.md](../../../docs/architecture/planner_vocabulary.md)）；
  禁止为了让某道评测题通过而增删词。

命中规则：**子串命中**（`hint in text`）。中文没有天然空格分词，确定性规划器
一直采用子串匹配，因此词表必须保持"短、专、无歧义"——不能放裸"费"这种会命中
"免费"的单字。

兜底契约：完全未命中任何领域时**不做猜测**，由 `RuleBasedPlanner` 返回
`needs_clarification`（回问用户），而不是像 Task 009 那样静默落到 billing。
"""

from __future__ import annotations

__all__ = [
    "DOMAINS",
    "DOMAIN_CAPABILITIES",
    "DOMAIN_HINTS",
    "DOMAIN_LABELS",
    "matched_domains",
    "matched_words",
]

#: 领域顺序即路由顺序：`routing_reason` 与子任务编号都按这个顺序生成。
DOMAINS: tuple[str, ...] = ("lease", "billing", "property")

#: 用户可见的中文标签（回问选项、路由理由都用它，避免只给英文领域名）。
DOMAIN_LABELS: dict[str, str] = {
    "lease": "合同/租约",
    "billing": "账单/费用",
    "property": "物业工单",
}

#: 每个领域对应的 Agent 能力名（Coordinator 按能力解析，不 import 具体 Agent）。
DOMAIN_CAPABILITIES: dict[str, str] = {
    "lease": "lease.query",
    "billing": "billing.statement",
    "property": "property.work_orders",
}

#: 领域 → 同义词（子串匹配）。来源逐词见 docs/architecture/planner_vocabulary.md。
#: 前 8~10 个词是 Task 009 原始规则表，其余为 Task 031 增补（每个都有来源依据）。
DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "lease": (
        # Task 009 原始词表
        "合同",
        "租约",
        "条款",
        "递增",
        "免租",
        "押金",
        "续租",
        "租期",
        # Task 031 增补
        "租赁",
    ),
    "billing": (
        # Task 009 原始词表
        "账单",
        "租金",
        "费用",
        "欠费",
        "付款",
        "核销",
        "多收",
        "少收",
        "金额",
        "发票",
        # Task 031 增补：既有欠费意图词表（Task 013 `baselines._ARREARS_HINTS`）
        "欠",
        "未交",
        "没交",
        "未收",
        "余额",
        "已收",
        "对账",
        "应收",
        # Task 031 增补：真实口语/业务单据说法
        "物业费",
        "管理费",
    ),
    "property": (
        # Task 009 原始词表
        "空调",
        "维修",
        "工单",
        "报修",
        "故障",
        "投诉",
        "漏水",
        "电梯",
        # Task 031 增补：口语说法（冷气/不制冷/空调不凉）
        "冷气",
        "不制冷",
        "空调不凉",
    ),
}


def _as_text(text: object) -> str:
    return "" if text is None else str(text)


def matched_domains(text: str) -> dict[str, tuple[str, ...]]:
    """返回"命中的领域 → 该领域命中的词"。

    - 只包含**真的有命中**的领域，键顺序与 `DOMAINS` 一致；
    - 完全未命中返回 `{}`（调用方据此走 clarification 兜底）；
    - 词按词表顺序给出，便于报告与排查复现。
    """

    content = _as_text(text)
    matched: dict[str, tuple[str, ...]] = {}
    for domain in DOMAINS:
        hits = tuple(hint for hint in DOMAIN_HINTS[domain] if hint in content)
        if hits:
            matched[domain] = hits
    return matched


def matched_words(text: str) -> tuple[str, ...]:
    """命中的全部词（按领域顺序、词表顺序去重），用于日志/调试。"""

    content = _as_text(text)
    words: dict[str, None] = {}
    for domain in DOMAINS:
        for hint in DOMAIN_HINTS[domain]:
            if hint in content:
                words.setdefault(hint, None)
    return tuple(words)
