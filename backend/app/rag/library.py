"""把 fixture 登记的文档挂到真实 PDF 上（Task 011）。

为什么需要这一层：
- `KnowledgeService` 只认识"文件"，fixture 只认识"文档元数据"，两者必须显式对齐；
- 页码/版本的一致性由这里统一校验：fixture 说 5.2 在第 12 页，真实 PDF 第 12 页就必须有 5.2；
- 缺失的文档（例如尚未电子化的附件B）**不生成占位文件**，检索时会真的查不到——
  这样"资料缺失"是真实结果，而不是被伪造的证据。

对齐失败直接抛 `DocumentMismatch`，不允许带着错误页码继续评测。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..fixtures.repository import FixtureRepository
from ..paths import DOCUMENT_DIR, DOCUMENT_FILES
from .service import DocumentIndex, KnowledgeService

__all__ = ["DocumentMismatch", "KnowledgeLibrary", "build_knowledge_library"]


class DocumentMismatch(RuntimeError):
    """fixture 声明的页码/条款与真实 PDF 内容不一致。"""


@dataclass(frozen=True)
class KnowledgeLibrary:
    service: KnowledgeService
    indexed: dict[str, DocumentIndex]
    missing_documents: tuple[str, ...]


def _snippets_by_document(repository: FixtureRepository) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for snippet in repository.snapshot().get("document_snippets", []):
        grouped.setdefault(snippet["document_id"], []).append(snippet)
    return grouped


def verify_snippets(
    service: KnowledgeService,
    *,
    document_id: str,
    document_version: int,
    snippets: list[dict],
) -> None:
    """fixture 的每条 snippet 必须能在索引里定位到同样的页码与条款号。"""

    for snippet in snippets:
        if snippet.get("document_version", 1) != document_version:
            continue
        hits = service.search(
            snippet["text"],
            document_id=document_id,
            document_version=document_version,
            top_k=5,
        )
        matched = [
            hit.chunk
            for hit in hits
            if hit.chunk.clause_id == snippet["clause_id"]
            and hit.chunk.page == snippet["page"]
        ]
        if not matched:
            located = [(hit.chunk.clause_id, hit.chunk.page) for hit in hits]
            raise DocumentMismatch(
                f"{document_id} 的条款 {snippet['clause_id']} 未在 PDF 第 {snippet['page']} 页定位到；"
                f"实际检索到: {located}"
            )


def build_knowledge_library(
    repository: FixtureRepository,
    *,
    document_dir: str | Path | None = None,
    strict: bool = True,
) -> KnowledgeLibrary:
    """索引所有已登记且有 PDF 的文档；缺文件的文档记入 `missing_documents`。"""

    base = Path(document_dir) if document_dir is not None else DOCUMENT_DIR
    service = KnowledgeService(as_of_date=repository.as_of_date)
    indexed: dict[str, DocumentIndex] = {}
    missing: list[str] = []

    snippets = _snippets_by_document(repository)
    for document in repository.snapshot().get("documents", []):
        document_id = document["id"]
        filename = DOCUMENT_FILES.get(document_id)
        if filename is None:
            missing.append(document_id)
            continue
        path = base / filename
        if not path.is_file():
            missing.append(document_id)
            continue
        version = document.get("version", 1)
        record = service.index_pdf(
            document_id=document_id,
            path=path,
            project_id=document["project_id"],
            document_version=version,
        )
        indexed[document_id] = record
        if strict:
            verify_snippets(
                service,
                document_id=document_id,
                document_version=version,
                snippets=snippets.get(document_id, []),
            )

    return KnowledgeLibrary(
        service=service, indexed=indexed, missing_documents=tuple(missing)
    )
