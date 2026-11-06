"""知识检索服务与引用验证（Task 011）。

两级验证（与 Runtime contracts §3.3 一致）：

- **L1 引用存在**：chunk 必须真实存在于索引，且 `document_version` 与页码/条款一致；
- **L2 引用支持结论**：用确定性的词元覆盖度判断摘录是否支持结论，并明确标注为启发式。

文档内容是**不可信输入**：它只能作为返回数据，不能改变工具策略、权限或提示词。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from .bm25 import BM25Index, tokenize
from .chunker import Chunk, chunk_pages, extract_pages

__all__ = [
    "CitationCheck",
    "DocumentIndex",
    "KnowledgeService",
    "RetrievedChunk",
]


@dataclass(frozen=True)
class DocumentIndex:
    document_id: str
    document_version: int
    project_id: str
    path: Path
    checksum_sha256: str
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class CitationCheck:
    chunk_id: str
    reference_exists: bool
    supports_claim: str  # supports | partial | unrelated
    coverage: float
    method: str = "token_coverage_heuristic"

    @property
    def acceptable(self) -> bool:
        return self.reference_exists and self.supports_claim in {"supports", "partial"}


class KnowledgeService:
    """按文档版本建立索引，并回答"条款在不在、能否支持结论"。"""

    def __init__(self, *, as_of_date: date | None = None) -> None:
        self._index = BM25Index()
        self._chunks: dict[str, Chunk] = {}
        self._documents: dict[tuple[str, int], DocumentIndex] = {}
        # 证据里需要"数据截止日"，由调用方注入（与 fixture 的 as_of_date 保持一致）
        self.as_of_date = as_of_date or date(2026, 11, 3)

    # ---------------- 索引 ----------------

    def index_pdf(
        self,
        *,
        document_id: str,
        path: str | Path,
        project_id: str,
        document_version: int = 1,
    ) -> DocumentIndex:
        pdf_path = Path(path)
        pages = extract_pages(pdf_path)
        chunks = chunk_pages(
            pages, document_id=document_id, document_version=document_version
        )
        checksum = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        self.remove_document(document_id, document_version)
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
            self._index.add(chunk.chunk_id, f"{chunk.clause_id} {chunk.text}")
        record = DocumentIndex(
            document_id=document_id,
            document_version=document_version,
            project_id=project_id,
            path=pdf_path,
            checksum_sha256=checksum,
            chunks=tuple(chunks),
        )
        self._documents[(document_id, document_version)] = record
        return record

    def remove_document(self, document_id: str, document_version: int) -> None:
        record = self._documents.pop((document_id, document_version), None)
        if record is None:
            return
        for chunk in record.chunks:
            self._index.remove(chunk.chunk_id)
            self._chunks.pop(chunk.chunk_id, None)

    def page_count(self, document_id: str, document_version: int = 1) -> int:
        record = self._documents[(document_id, document_version)]
        return len(PdfReader(str(record.path)).pages)

    # ---------------- 检索 ----------------

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        document_version: int | None = None,
        project_ids: frozenset[str] | None = None,
        top_k: int = 3,
    ) -> list[RetrievedChunk]:
        """按分数检索条款。

        `project_ids` 是**数据隔离边界**：
        - `None` 表示不限制（仅供内部/测试直接使用）；
        - 空集合表示调用方没有任何项目授权，必须返回空结果（默认拒绝）。
        """

        results = self._index.search(query, top_k=max(top_k * 4, top_k))
        retrieved: list[RetrievedChunk] = []
        for chunk_id, score in results:
            chunk = self._chunks[chunk_id]
            if document_id is not None and chunk.document_id != document_id:
                continue
            if document_version is not None and chunk.document_version != document_version:
                continue
            if project_ids is not None:
                record = self._documents.get(
                    (chunk.document_id, chunk.document_version)
                )
                if record is None or record.project_id not in project_ids:
                    continue
            retrieved.append(RetrievedChunk(chunk=chunk, score=score))
            if len(retrieved) >= top_k:
                break
        return retrieved

    def project_of(self, document_id: str, document_version: int) -> str | None:
        record = self._documents.get((document_id, document_version))
        return None if record is None else record.project_id

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    # ---------------- 引用验证 ----------------

    def verify_citation(
        self, *, chunk_id: str, claim: str, document_version: int | None = None
    ) -> CitationCheck:
        chunk = self._chunks.get(chunk_id)
        if chunk is None:
            return CitationCheck(
                chunk_id=chunk_id,
                reference_exists=False,
                supports_claim="unrelated",
                coverage=0.0,
            )
        if document_version is not None and chunk.document_version != document_version:
            return CitationCheck(
                chunk_id=chunk_id,
                reference_exists=False,
                supports_claim="unrelated",
                coverage=0.0,
            )
        claim_tokens = {token for token in tokenize(claim) if len(token) > 1}
        chunk_tokens = set(tokenize(chunk.text))
        if not claim_tokens:
            coverage = 0.0
        else:
            coverage = len(claim_tokens & chunk_tokens) / len(claim_tokens)
        if coverage >= 0.5:
            verdict = "supports"
        elif coverage >= 0.2:
            verdict = "partial"
        else:
            verdict = "unrelated"
        return CitationCheck(
            chunk_id=chunk_id,
            reference_exists=True,
            supports_claim=verdict,
            coverage=round(coverage, 3),
        )