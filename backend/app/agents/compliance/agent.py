"""Compliance Agent：合规与风险检查。

阶段 0 仅为骨架，默认在配置中禁用，用于验证「能力被禁用时系统如何报告」。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from ..base.errors import AgentError, ErrorCode


class ComplianceAgent(BaseAgent):
    name = "compliance"
    version = "0.1.0"
    description = "合同合规检查与租约风险提示"
    capabilities = frozenset({"compliance.check"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        raise AgentError(
            "ComplianceAgent 业务逻辑尚未实现（阶段 0：仅完成架构骨架）",
            code=ErrorCode.NOT_IMPLEMENTED,
            retryable=False,
            details={"capability": request.capability},
        )
