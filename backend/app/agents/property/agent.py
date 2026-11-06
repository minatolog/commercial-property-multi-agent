"""Property Agent：维修与投诉工单事实查询（Task 009）。

只返回工单事实（次数、类别、状态、时间线），不判定责任归属，
也不推断"应当减免"——那属于人工决策。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest
from ..base.errors import AgentError, ErrorCode
from ..base.tool_backed import ToolBackedAgent


class PropertyAgent(ToolBackedAgent):
    name = "property"
    version = "1.0.0"
    description = "维修工单与投诉记录查询"
    capabilities = frozenset({"property.work_orders"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        payload = request.payload or {}
        lease_id = str(payload.get("lease_id") or "").strip()
        unit_id = str(payload.get("unit_id") or "").strip()
        if not lease_id and not unit_id:
            raise AgentError(
                "payload 需要 lease_id 或 unit_id",
                code=ErrorCode.INVALID_REQUEST,
                retryable=False,
            )

        tool_payload = {}
        if lease_id:
            tool_payload["lease_id"] = lease_id
        if unit_id:
            tool_payload["unit_id"] = unit_id
        category = str(payload.get("category") or "").strip()
        if category:
            tool_payload["category"] = category

        execution = await self._invoke_tool(
            "property.work_orders.read", tool_payload, context
        )
        data = execution.data or {}
        open_orders = [
            item for item in data.get("work_orders", []) if item.get("status") != "closed"
        ]
        return AgentOutput(
            data={
                "capability": request.capability,
                **data,
                "open_work_order_ids": [
                    item["work_order_id"] for item in open_orders
                ],
                "open_work_order_count": len(open_orders),
                "evidence": self._evidence_payload(execution),
            },
            warnings=(
                (f"存在 {len(open_orders)} 条未关闭工单",) if open_orders else ()
            ),
        )