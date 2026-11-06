"""能力级最低结果契约（Task 021 / N4）：没有取到事实就不算完成。

问题背景：`LLMToolAgent` 只要模型给出非空文本就结束循环，图又把"Agent 返回成功"
当成"子任务证据充分"。于是模型完全可以一次工具都不调、直接回一句"账单没有问题"，
而调查结果仍是 `verdict=supported` / `completeness=complete`。

为什么把契约放在这里而不是写进 Prompt：

- Prompt 是**请求**，契约是**约束**。模型可以忽略前者，代码不能忽略后者；
- 同一个契约要被两处使用——Agent 出口（拿不到事实就别返回成功）与图核验
  （不轻信 Agent 自称成功），单点定义才能保证两处口径一致；
- 换模型、换引擎（deterministic / llm）时契约不变，因此这里只描述
  "这个能力必须产出哪些字段"，不描述如何取数。

契约只覆盖**业务取数能力**。没有登记的 capability 视为"允许纯说明"，
不做字段要求——把未知能力也硬填一张表，等于用编造的门槛制造通过/失败。
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["REQUIRED_RESULT_FIELDS", "required_fields", "check_capability_output"]


#: capability → 必须由**工具结果**填充的输出字段（空表示允许无取数）。
#:
#: 这些字段全部由工具输出搬运而来（见 `facts.py` / 各确定性 Agent），
#: 因此"字段缺失"等价于"这次没有拿到该能力的真实数据"。
REQUIRED_RESULT_FIELDS: dict[str, tuple[str, ...]] = {
    "billing.statement": (
        "lease_id",
        "invoiced_total",
        "paid_total",
        "outstanding_total",
    ),
    "billing.arrears_check": ("lease_id", "outstanding_total"),
    "property.work_orders": ("work_order_count", "open_count"),
    "lease.query": ("lease",),
    "lease.renewal_evaluation": ("lease",),
}


def required_fields(capability: str) -> tuple[str, ...]:
    return REQUIRED_RESULT_FIELDS.get(capability, ())


def check_capability_output(
    capability: str, output: Mapping[str, Any] | None
) -> list[str]:
    """返回缺失的必需字段说明；空列表表示满足契约。"""

    fields = required_fields(capability)
    if not fields:
        return []
    data: Mapping[str, Any] = output or {}
    return [
        f"能力 {capability} 缺少必需事实 {name}"
        for name in fields
        if not _filled(data.get(name))
    ]


def _filled(value: Any) -> bool:
    """字段是否真的带着工具结果。

    `0` / `False` / 空列表都是**有效取值**（例如"零条工单"），
    只有 `None`、空字符串、`"None"` 字符串与"全为空的映射"才算缺失。
    """

    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "None", "none", "NaN"}
    if isinstance(value, Mapping):
        return any(_filled(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return True
    return True
