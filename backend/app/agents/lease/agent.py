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
        clauses, clause_evidence, clause_warnings = await self._retrieve_clauses(
            request=request,
            context=context,
            lease_id=lease_id,
            document_ids=[str(item) for item in data.get("document_ids") or []],
            signed_document_ids=[
                str(item) for item in data.get("signed_document_ids") or []
            ],
            draft_document_ids=[
                str(item) for item in data.get("draft_document_ids") or []
            ],
        )
        warnings = list(clause_warnings)
        draft_documents = [
            str(item) for item in data.get("draft_document_ids") or []
        ]
        if draft_documents and not any(
            clause.get("document_status") == "draft" for clause in clauses
        ):
            warnings.append(
                "租约引用未签署草案（不得作为生效依据）: " + ", ".join(draft_documents)
            )

        if request.capability == "lease.query":
            return AgentOutput(
                data={
                    "capability": request.capability,
                    "lease": lease,
                    "rules": data.get("rules", []),
                    "documents": data.get("document_ids", []),
                    "signed_documents": data.get("signed_document_ids", []),
                    "draft_documents": draft_documents,
                    "missing_documents": data.get("missing_document_ids", []),
                    "clauses": clauses,
                    "clause_evidence": clause_evidence,
                    "evidence": self._evidence_payload(execution),
                },
                warnings=warnings,
            )

        # renewal_evaluation：只汇总事实，并显式标注需要人工判断的部分
        rules = data.get("rules", []) or []
        if data.get("missing_document_ids"):
            warnings.append(
                "租约引用但未电子化的文档: "
                + ", ".join(data.get("missing_document_ids", []))
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
                "clauses": clauses,
                "clause_evidence": clause_evidence,
                "requires_human_decision": True,
                "decision_reason": "续租定价与商务条件属于人工决策，本 Agent 只提供事实依据",
                "evidence": self._evidence_payload(execution),
            },
            warnings=warnings,
        )

    async def _retrieve_clauses(
        self,
        *,
        request: AgentRequest,
        context: AgentContext,
        lease_id: str,
        document_ids: list[str],
        signed_document_ids: list[str] | None = None,
        draft_document_ids: list[str] | None = None,
    ) -> tuple[list[dict], list[dict], list[str]]:
        """读取**本租约适用且已签署**的合同条款作为可追溯证据。

        Task 016（F7）：只按项目过滤是不够的——同项目另一个租约的合同属于不同文档。
        因此把 `lease.lookup` 返回的文档范围传下去，项目级公共文档另行放行。

        Task 017（R4）：默认只检索**已签署**文档。未签署草案即使属于本租约，
        也不能当作生效依据；它只能出现在 `draft_documents` 提示里（或调用方
        显式要求比较草案时单列为 `document_draft` 证据）。

        未授权或未注册 `document.search` 时**不报错**，只降级为"无条款证据"并给出警告：
        条款检索是增强能力，不应该让租约事实查询整体失败。
        """

        query = str(request.payload.get("query") or "").strip()
        if not query or "document.search" not in self.config.allowed_tools:
            return [], [], []
        effective_documents = (
            list(signed_document_ids)
            if signed_document_ids
            else [
                document_id
                for document_id in document_ids
                if document_id not in set(draft_document_ids or ())
            ]
        )
        try:
            execution = await self._invoke_tool(
                "document.search",
                {
                    "query": query,
                    "top_k": 3,
                    "document_ids": effective_documents,
                    "include_project_documents": True,
                    "include_drafts": False,
                },
                context,
            )
        except AgentError as exc:
            return [], [], [
                f"条款检索不可用（{exc.code.value}），本次结论不含合同条款证据"
            ]
        payload = execution.data or {}
        clauses = [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item["document_id"],
                "document_version": item["document_version"],
                "document_scope": item.get("document_scope", "unknown"),
                "document_status": item.get("document_status", "signed"),
                "page": item["page"],
                "clause_id": item["clause_id"],
                "excerpt": item["excerpt"],
            }
            for item in payload.get("results", [])
        ]
        if not clauses:
            return [], [], [f"租约 {lease_id} 的适用文档未检索到匹配条款"]
        return clauses, self._evidence_payload(execution), []


def _require_lease_id(payload: dict) -> str:
    lease_id = str(payload.get("lease_id") or "").strip()
    if not lease_id:
        raise AgentError(
            "payload 缺少 lease_id",
            code=ErrorCode.INVALID_REQUEST,
            retryable=False,
        )
    return lease_id