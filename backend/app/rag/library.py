"""把文档目录（`DocumentCatalog`）挂到真实 PDF 上（Task 011 / 016）。

为什么需要这一层：
- `KnowledgeService` 只认识"文件"，文档目录只认识"元数据"，两者必须显式对齐；
- 页码/版本的一致性由这里统一校验：fixture 说 5.2 在第 12 页，真实 PDF 第 12 页就必须有 5.2；
- 缺失的文档（例如尚未电子化的附件B）**不生成占位文件**，检索时会真的查不到——
  这样"资料缺失"是真实结果，而不是被伪造的证据。

Task 016 改动（F3/F7）：
- 入参从 `FixtureRepository` 换成 `DocumentCatalog`，因此只读数据库后端可用；
- 只有目录能提供 snippets 时才做页码对齐校验，校验结果显式记录在 `snippets_verified`；
- 每个文档记录 `lease_id`，供"条款检索按租约限定"使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..paths import DOCUMENT_DIR, DOCUMENT_FILES
from .catalog import DocumentCatalog, DocumentMeta, catalog_for
from .service import DocumentIndex, KnowledgeService

__all__ = [
    "DocumentMismatch",
    "KnowledgeLibrary",
    "build_knowledge_library",
    "fixture_catalog",
    "verify_snippets",
]


class DocumentMismatch(RuntimeError):
    """fixture 声明的页码/条款与真实 PDF 内容不一致。"""


@dataclass(frozen=True)
class KnowledgeLibrary:
    service: KnowledgeService
    indexed: dict[str, DocumentIndex]
    missing_documents: tuple[str, ...]
    #: document_id → 归属信息（项目 / 租约 / 版本 / 适用范围）
    documents: dict[str, DocumentMeta] = field(default_factory=dict)
    #: 是否执行了"fixture 页码 == 真实页码"的对齐校验
    snippets_verified: bool = False

    def document_ids_for_lease(self, lease_id: str | None) -> tuple[str, ...]:
        """返回某租约**适用**的文档集合（本租约文档 + 项目级公共文档）。"""

        if not lease_id:
            return tuple(
                meta.document_id
                for meta in self.documents.values()
                if meta.lease_id is None
            )
        return tuple(
            meta.document_id
            for meta in self.documents.values()
            if meta.lease_id in (None, lease_id)
        )

    def scope_of(self, document_id: str) -> str:
        meta = self.documents.get(document_id)
        return "unknown" if meta is None else meta.scope


def fixture_catalog(repository: Any) -> DocumentCatalog:
    """fixture 仓库 → 文档目录（文件名来自仓库内的映射）。"""

    return catalog_for(repository, filename_resolver=DOCUMENT_FILES.get)


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
    catalog: DocumentCatalog,
    *,
    as_of_date: date | None = None,
    document_dir: str | Path | None = None,
    strict: bool = True,
) -> KnowledgeLibrary:
    """索引目录中所有有 PDF 的文档；缺文件的文档记入 `missing_documents`。

    没有文件名的文档（数据库目录通常如此）同样记入缺失——不伪造索引。
    """

    base = Path(document_dir) if document_dir is not None else DOCUMENT_DIR
    service = KnowledgeService(as_of_date=as_of_date)
    indexed: dict[str, DocumentIndex] = {}
    documents: dict[str, DocumentMeta] = {}
    missing: list[str] = []
    verified = False

    for meta in catalog.list_documents():
        filename = meta.filename or DOCUMENT_FILES.get(meta.document_id)
        if filename is None:
            missing.append(meta.document_id)
            continue
        path = base / filename
        if not path.is_file():
            missing.append(meta.document_id)
            continue
        record = service.index_pdf(
            document_id=meta.document_id,
            path=path,
            project_id=meta.project_id,
            lease_id=meta.lease_id,
            document_version=meta.version,
        )
        indexed[meta.document_id] = record
        documents[meta.document_id] = meta
        snippets = catalog.snippets(meta.document_id)
        if strict and snippets:
            verify_snippets(
                service,
                document_id=meta.document_id,
                document_version=meta.version,
                snippets=snippets,
            )
            verified = True

    return KnowledgeLibrary(
        service=service,
        indexed=indexed,
        missing_documents=tuple(missing),
        documents=documents,
        snippets_verified=verified,
    )
