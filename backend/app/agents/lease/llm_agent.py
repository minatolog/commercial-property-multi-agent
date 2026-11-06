"""Lease Agent 的 LLM 引擎（Task 018）。

与 `LeaseAgent` 共用同一份 YAML、同一个 Prompt、同一套工具白名单；
差别只在于"由谁决定调哪个工具"：本实现交给模型，事实仍取自工具输出。

单独一个类而不是一个开关，是因为 K2 要求"配置的 name/version/capabilities 与实现一致"，
而 descriptor 是类属性——一个通用类无法同时代表三个领域 Agent。
"""

from __future__ import annotations

from ..base.llm_agent import LLMToolAgent


class LeaseLLMAgent(LLMToolAgent):
    name = "lease"
    version = "1.0.0"
    description = "租约条款查询、租金结构解读与续租评估（LLM 引擎）"
    capabilities = frozenset({"lease.query", "lease.renewal_evaluation"})
    tool_prefixes = ("lease.", "document.")
