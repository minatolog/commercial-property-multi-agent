"""Lease Agent：租约条款查询与续租评估。

阶段 0 仅为骨架：接口、配置、Prompt 已就位，业务逻辑待实现。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from ..base.errors import AgentError, ErrorCode


class LeaseAgent(BaseAgent):
    name = "lease"
    version = "0.1.0"
    description = "租约条款查询、租金结构解读与续租评估"
    capabilities = frozenset({"lease.query", "lease.renewal_evaluation"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        raise AgentError(
            "LeaseAgent 业务逻辑尚未实现（阶段 0：仅完成架构骨架）",
            code=ErrorCode.NOT_IMPLEMENTED,
            retryable=False,
            details={"capability": request.capability},
        )
