"""LangChain interface for contract clauses in a trusted search scope."""

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from .service import KnowledgeService


class ContractRetriever(BaseRetriever):
    """Bind scope at construction. The query is the only input at invocation."""

    service: KnowledgeService = Field(exclude=True, repr=False)
    project_ids: frozenset[str]
    document_ids: frozenset[str] | None
    document_statuses: frozenset[str]
    document_id: str | None = None
    document_version: int | None = None
    top_k: int = Field(default=3, ge=1, le=10)

    def _get_relevant_documents(self, query: str) -> list[Document]:
        documents = []
        hits = self.service.search(
            query,
            project_ids=self.project_ids,
            document_ids=self.document_ids,
            document_statuses=self.document_statuses,
            document_id=self.document_id,
            document_version=self.document_version,
            top_k=self.top_k,
        )
        for hit in hits:
            chunk = hit.chunk
            document_id, version = chunk.document_id, chunk.document_version
            documents.append(Document(
                id=chunk.chunk_id,
                page_content=chunk.text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "document_id": document_id,
                    "document_version": version,
                    "project_id": self.service.project_of(document_id, version),
                    "document_scope": self.service.scope_of(document_id, version) or "unknown",
                    "document_status": self.service.status_of(document_id, version) or "unknown",
                    "lease_id": self.service.lease_of(document_id, version),
                    "page": chunk.page,  # PDF 的业务页码，沿用索引原值。
                    "clause_id": chunk.clause_id,
                    "score": hit.score,
                    "synthetic": chunk.synthetic,
                },
            ))
        return documents
