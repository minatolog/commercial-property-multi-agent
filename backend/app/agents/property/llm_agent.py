"""Property Agent 的 LLM 引擎（Task 018）。配置与工具白名单与 `PropertyAgent` 完全一致。"""

from __future__ import annotations

from ..base.llm_agent import LLMToolAgent


class PropertyLLMAgent(LLMToolAgent):
    name = "property"
    version = "1.0.0"
    description = "维修工单与投诉记录查询（LLM 引擎）"
    capabilities = frozenset({"property.work_orders"})
    tool_prefixes = ("property.",)
