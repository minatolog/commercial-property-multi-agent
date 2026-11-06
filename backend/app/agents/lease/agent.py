"""Lease Agent：租约条款查询（Task 009）。

职责边界：只返回租约事实与计费规则，不做主观定价判断，也不计算金额
（金额由 Billing 工具用 Decimal 计算）。
"""

from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest
from ..base.errors import AgentError, ErrorCode
from ..base.tool_backed import ToolBackedAgent


class LeaseAgent(ToolBackedAgent):
    name = "lease"
    version = "1.0.0"
    description = "租约条款查询与租金结构解读"
    capabilities = frozenset({"lease.query", "lease.renewal_evaluation"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        lease_id = _require_lease_id(request.payload)
        execution = await self._invoke_tool("lease.lookup", {"lease_id": lease_id}, context)
        data = execution.data or {}
        # 工具返回扁平结构：租约字段与规则并列（见 fixture_tools.LeaseLookupOutput）
        lease = {
            key: data.get(key)
            for key in (
                "lease_id",
                "lease_no",
                "project_id",
                "unit_id",
                "unit_code",
                "tenant_id",
                "currency",
                "deposit_amount",
                "start_date",
                "end_date",
                "status",
            )
        }

        if request.capability == "lease.query":
            return AgentOutput(
                data={
                    "capability": request.capability,
                    "lease": lease,
                    "rules": data.get("rules", []),
                    "documents": data.get("document_ids", []),
                    "missing_documents": data.get("missing_document_ids", []),
                    "evidence": self._evidence_payload(execution),
                }
            )

        # renewal_evaluation：只汇总事实，并显式标注需要人工判断的部分
        rules = data.get("rules", []) or []
        warnings = (
            (
                "租约引用但未电子化的文档: "
                + ", ".join(data.get("missing_document_ids", []))
            )
            if data.get("missing_document_ids")
            else ()
        )
        return AgentOutput(
            data={
                "capability": request.capability,
                "lease": lease,
                "rent_rules": [rule for rule in rules if rule.get("charge_type") == "rent"],
                "renewal_facts": {
                    "end_date": lease.get("end_date"),
                    "billing_cycle": lease.get("billing_cycle"),
                    "currency": lease.get("currency"),
                },
                "requires_human_decision": True,
                "decision_reason": "续租定价与商务条件属于人工决策，本 Agent 只提供事实依据",
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