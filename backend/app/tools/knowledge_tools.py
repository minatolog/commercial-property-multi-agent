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
    #: 额外允许**项目级公共**文档（租约无关的制度/规范）
    include_project_documents: bool = True
    top_k: int = Field(default=3, ge=1, le=10)


class DocumentClauseOut(_StrictModel):
    chunk_id: str
    document_id: str
    document_version: int
    project_id: str
    #: `lease`=本租约合同；`project`=项目级公共文档
    document_scope: str
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
    ) -> None:
        self._service = service
        self._library = library
        self._lease_id = lease_id

    async def invoke(
        self, payload: DocumentSearchInput, context: AgentContext
    ) -> ToolInvocation:
        allowed: frozenset[str] | None = None
        if payload.document_ids is not None:
            allowed = frozenset(payload.document_ids)
            if payload.include_project_documents and self._library is not None:
                allowed = allowed | frozenset(
                    meta.document_id
                    for meta in self._library.documents.values()
                    if meta.lease_id is None
                )
        hits = self._service.search(
            payload.query,
            document_id=payload.document_id,
            document_version=payload.document_version,
            project_ids=context.project_ids,
            document_ids=allowed,
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
