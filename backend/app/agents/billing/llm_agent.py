"""Billing Agent 的 LLM 引擎（Task 018）。配置与工具白名单与 `BillingAgent` 完全一致。"""

from __future__ import annotations

from ..base.llm_agent import LLMToolAgent


class BillingLLMAgent(LLMToolAgent):
    name = "billing"
    version = "1.1.0"
    description = "账单查询、收款核销事实与欠费核对（LLM 引擎）"
    capabilities = frozenset({"billing.statement", "billing.arrears_check"})
    tool_prefixes = ("billing.",)
