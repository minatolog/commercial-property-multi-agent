"""Billing Agent：账单查询与费用结构说明。

阶段 0 仅为骨架。金额计算属于确定性逻辑，必须放在 tools/ 中，
不得由本 Agent 用 LLM 自由生成。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from ..base.errors import AgentError, ErrorCode


class BillingAgent(BaseAgent):
    name = "billing"
    version = "0.1.0"
    description = "物业账单查询、费用构成说明与欠费核对"
    capabilities = frozenset({"billing.statement", "billing.arrears_check"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        raise AgentError(
            "BillingAgent 业务逻辑尚未实现（阶段 0：仅完成架构骨架）",
            code=ErrorCode.NOT_IMPLEMENTED,
            retryable=False,
            details={"capability": request.capability},
        )
