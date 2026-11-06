"""合同条款检索工具（Task 011）。

输出 `document_clause` 类证据，包含文档 ID、版本、**真实 PDF 页码**、条款号与原文摘录。

两条硬约束：

1. **项目隔离**：只返回调用方 `AgentContext.project_ids` 授权范围内的文档；
   空授权即零结果，不做"默认可见"。
2. **文档是不可信数据**：条款文本只作为返回值出现，即使其中写着"忽略以上指令"，
   也不会改变工具策略、权限或后续提示词。
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from ..agents.base.contracts import AgentContext
from ..rag.service import KnowledgeService
from ..runtime.types import EvidenceDraft
from .base import BaseTool, ToolInvocation
from .fixture_tools import _StrictModel

__all__ = ["DocumentSearchInput", "DocumentSearchTool"]


class DocumentSearchInput(_StrictModel):
    query: str = Field(min_length=1, max_length=200)
    document_id: str | None = None
    document_version: int | None = Field(default=None, ge=1)
    #: 只允许检索这些文档（由调用方按租约解析；空列表等价于"不允许任何文档"）
    document_ids: list[str] | None = None
    #: 本次任务的目标租约。给了它，工具就**自己**解析适用文档集合，
    #: 不再依赖模型主动填 `document_ids`（Task 021 / N3）。
    lease_id: str | None = None
    #: 额外允许**项目级公共**文档（租约无关的制度/规范）
    include_project_documents: bool = True
    #: 是否同时检索**未签署草案**（Task 017 / R4）。默认否：
    #: 草案不得作为生效依据，只能显式比较时单列。
    include_drafts: bool = False
    top_k: int = Field(default=3, ge=1, le=10)


class DocumentClauseOut(_StrictModel):
    chunk_id: str
    document_id: str
    document_version: int
    project_id: str
    #: `lease`=本租约合同；`project`=项目级公共文档
    document_scope: str
    #: `signed`=已签署生效；`draft`=未签署草案
    document_status: str = "signed"
    lease_id: str | None = None
    page: int
    clause_id: str
    excerpt: str
    score: float
    synthetic: bool


class DocumentSearchOutput(_StrictModel):
    query: str
    result_count: int
    results: list[DocumentClauseOut]


class DocumentSearchTool(BaseTool):
    name: ClassVar[str] = "document.search"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = "在合同文本中检索条款，返回可定位到页码与原文的证据"
    required_permissions: ClassVar[frozenset[str]] = frozenset({"lease.read"})
    timeout_seconds: ClassVar[float] = 5.0
    max_attempts: ClassVar[int] = 1
    input_model: ClassVar[type] = DocumentSearchInput
    output_model: ClassVar[type] = DocumentSearchOutput

    def __init__(
        self,
        service: KnowledgeService,
        *,
        library: Any = None,
        lease_id: str | None = None,
        require_scope: bool = True,
    ) -> None:
        self._service = service
        self._library = library
        self._lease_id = lease_id
        #: Agent 调用必须能确定范围；CLI 的交互式检索才允许"全库搜索"
        self._require_scope = require_scope

    def _resolve_allowed(
        self, payload: DocumentSearchInput, *, statuses: frozenset[str]
    ) -> frozenset[str] | None:
        """解析本次允许的文档集合（Task 021 / N3）。

        优先级：可信的 `lease_id`（调用方/scope 注入）> 模型给的 `document_ids`。

        为什么必须以租约为准：模型可以省略 `document_ids`，一省略就等于"整个项目"，
        于是同项目另一个租约的合同会进入本租约的报告。这里由工具自己解析租约的
        适用文档集，再与模型显式给出的集合**取交集**——模型既不能省略扩大到项目，
        也不能点名别的租约的合同。

        既没有 `lease_id` 也没有 `document_ids` 时：受控调用（`require_scope=True`）
        返回**空集合**（默认拒绝），而不是"不限"。
        """

        if self._library is None:
            return None if payload.document_ids is None else frozenset(payload.document_ids)

        lease_id = payload.lease_id or self._lease_id
        requested: frozenset[str] | None = (
            None if payload.document_ids is None else frozenset(payload.document_ids)
        )
        if not lease_id:
            if requested is None:
                return frozenset() if self._require_scope else None
            if not payload.include_project_documents:
                return requested
            return requested | frozenset(
                self._library.project_document_ids(
                    statuses=("signed", "draft") if payload.include_drafts else ("signed",)
                )
            )

        allowed = set(self._library.document_ids_for_lease(lease_id, statuses=tuple(statuses)))
        if not payload.include_project_documents:
            allowed = {
                document_id
                for document_id in allowed
                if self._library.scope_of(document_id) != "project"
            }
        if requested is not None:
            allowed &= set(requested)
        return frozenset(allowed)

    async def invoke(
        self, payload: DocumentSearchInput, context: AgentContext
    ) -> ToolInvocation:
        statuses = (
            frozenset({"signed", "draft"}) if payload.include_drafts else frozenset({"signed"})
        )
        allowed = self._resolve_allowed(payload, statuses=statuses)
        hits = self._service.search(
            payload.query,
            document_id=payload.document_id,
            document_version=payload.document_version,
            project_ids=context.project_ids,
            document_ids=allowed,
            document_statuses=statuses,
            top_k=payload.top_k,
        )
        results: list[DocumentClauseOut] = []
        for hit in hits:
            project_id = self._service.project_of(
                hit.chunk.document_id, hit.chunk.document_version
            )
            if project_id is None:  # pragma: no cover - search 已保证记录存在
                continue
            results.append(
                DocumentClauseOut(
                    chunk_id=hit.chunk.chunk_id,
                    document_id=hit.chunk.document_id,
                    document_version=hit.chunk.document_version,
                    project_id=project_id,
                    document_scope=(
                        self._service.scope_of(
                            hit.chunk.document_id, hit.chunk.document_version
                        )
                        or "unknown"
                    ),
                    document_status=(
                        self._service.status_of(
                            hit.chunk.document_id, hit.chunk.document_version
                        )
                        or "unknown"
                    ),
                    lease_id=self._service.lease_of(
                        hit.chunk.document_id, hit.chunk.document_version
                    ),
                    page=hit.chunk.page,
                    clause_id=hit.chunk.clause_id,
                    excerpt=hit.chunk.text,
                    score=hit.score,
                    synthetic=hit.chunk.synthetic,
                )
            )
        evidence = tuple(
            EvidenceDraft(
                evidence_id=item.chunk_id,
                kind="document_clause",
                project_id=item.project_id,
                dataset_version="agent-first-v1",
                as_of_date=self._service.as_of_date,
                entity="document",
                record_id=item.document_id,
                fields={
                    "document_id": item.document_id,
                    "document_version": item.document_version,
                    "document_scope": item.document_scope,
                    "document_status": item.document_status,
                    "lease_id": item.lease_id,
                    "page": item.page,
                    "clause_id": item.clause_id,
                    "excerpt": item.excerpt,
                },
            )
            for item in results
        )
        return ToolInvocation(
            data=DocumentSearchOutput(
                query=payload.query, result_count=len(results), results=results
            ).model_dump(),
            evidence=evidence,
        )
