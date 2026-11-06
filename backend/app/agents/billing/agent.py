"""Billing Agent：账单与欠费事实查询（Task 009）。

金额一律由 `billing.*` 工具用 Decimal 计算；本 Agent 只做参数翻译与结构化包装。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest
from ..base.errors import AgentError, ErrorCode
from ..base.tool_backed import ToolBackedAgent


class BillingAgent(ToolBackedAgent):
    name = "billing"
    version = "1.1.0"
    description = "账单查询、收款核销事实与欠费核对"
    capabilities = frozenset({"billing.statement", "billing.arrears_check"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        lease_id = _require_lease_id(request.payload)
        if request.capability == "billing.statement":
            execution = await self._invoke_tool(
                "billing.statement.read", {"lease_id": lease_id}, context
            )
        else:
            execution = await self._invoke_tool(
                "billing.arrears.calculate", {"lease_id": lease_id}, context
            )

        data = execution.data or {}
        warnings: tuple[str, ...] = ()
        if data.get("rent_variance_total") not in (None, "0.00"):
            warnings = (f"账单租金与合同规则存在差额: {data['rent_variance_total']}",)

        return AgentOutput(
            data={
                "capability": request.capability,
                **data,
                "evidence": self._evidence_payload(execution),
            },
            warnings=warnings,
        )


def _require_lease_id(payload: dict) -> str:
    lease_id = str(payload.get("lease_id") or "").strip()
    if not lease_id:
        raise AgentError(
            "payload 缺少 lease_id",
            code=ErrorCode.INVALID_REQUEST,
            retryable=False,
        )
    return lease_id