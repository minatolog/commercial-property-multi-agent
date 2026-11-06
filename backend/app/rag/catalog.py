"""文档目录契约（Task 016，修复 F3/F7）。

问题背景：知识库装配直接调用 `FixtureRepository.snapshot()`，
于是任何非 fixture 数据源（如只读 SQLite 仓库）在接入 RAG 后都会崩溃；
同时"项目范围"被当成"合同归属"，导致同项目另一个租约的合同被当作本租约证据。

这里的做法：

1. 定义一个小接口 `DocumentCatalog`（列出文档 + 给出来源片段），装配层注入；
2. fixture 与数据库各自实现一个适配器，知识库不再认识 `snapshot()`；
3. `DocumentMeta` 显式携带 `lease_id`：
   - 有 `lease_id` → **租约适用**文档（只能用于该租约）；
   - `lease_id is None` → **项目级公共**文档（如物业制度），项目内共享。

`snippets()` 只有 fixture 能提供（用于页码对齐校验）；数据库目录返回空，
此时知识库会记为"未做页码对齐校验"，而不是假装校验过。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol, runtime_checkable

__all__ = [
    "DocumentCatalog",
    "DocumentMeta",
    "FixtureDocumentCatalog",
    "StaticDocumentCatalog",
    "catalog_for",
]


@dataclass(frozen=True)
class DocumentMeta:
    document_id: str
    project_id: str
    version: int = 1
    #: `None` 表示项目级公共文档（适用于该项目下所有租约）
    lease_id: str | None = None
    filename: str | None = None
    document_status: str = "signed"

    @property
    def scope(self) -> str:
        return "lease" if self.lease_id else "project"


@runtime_checkable
class DocumentCatalog(Protocol):
    """只读文档目录。实现方不得在这里做权限判断——权限由调用方上下文决定。"""

    def list_documents(self) -> list[DocumentMeta]:
        ...

    def snippets(self, document_id: str) -> list[dict[str, Any]]:
        ...


class StaticDocumentCatalog:
    """内存目录：数据库适配、测试、临时索引都用它。"""

    def __init__(
        self,
        documents: Iterable[DocumentMeta],
        *,
        snippets: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._documents = list(documents)
        self._snippets = dict(snippets or {})

    def list_documents(self) -> list[DocumentMeta]:
        return list(self._documents)

    def snippets(self, document_id: str) -> list[dict[str, Any]]:
        return list(self._snippets.get(document_id, ()))


class FixtureDocumentCatalog:
    """fixture 适配器：把 `documents` / `document_snippets` 映射成目录。"""

    def __init__(self, repository: Any, *, filename_resolver: Any = None) -> None:
        self._repository = repository
        self._filename_resolver = filename_resolver

    def list_documents(self) -> list[DocumentMeta]:
        snapshot = self._repository.snapshot()
        documents: list[DocumentMeta] = []
        for raw in snapshot.get("documents", []):
            document_id = str(raw["id"])
            filename = (
                self._filename_resolver(document_id)
                if self._filename_resolver is not None
                else raw.get("filename")
            )
            documents.append(
                DocumentMeta(
                    document_id=document_id,
                    project_id=str(raw["project_id"]),
                    version=int(raw.get("version", 1)),
                    lease_id=raw.get("lease_id"),
                    filename=filename,
                    document_status=str(raw.get("document_status", "signed")),
                )
            )
        return documents

    def snippets(self, document_id: str) -> list[dict[str, Any]]:
        snapshot = self._repository.snapshot()
        return [
            snippet
            for snippet in snapshot.get("document_snippets", [])
            if snippet.get("document_id") == document_id
        ]


def catalog_for(repository: Any, *, filename_resolver: Any = None) -> DocumentCatalog:
    """按仓库类型选择目录实现（鸭子类型，不 import fixture 具体类）。"""

    if hasattr(repository, "snapshot") and callable(repository.snapshot):
        return FixtureDocumentCatalog(repository, filename_resolver=filename_resolver)

    lister = getattr(repository, "documents", None)
    if not callable(lister):
        raise TypeError(
            f"{type(repository).__name__} 既没有 snapshot() 也没有 documents()，"
            "无法作为文档目录使用"
        )
    metas = [
        DocumentMeta(
            document_id=str(item["id"]),
            project_id=str(item["project_id"]),
            version=int(item.get("version", 1)),
            lease_id=item.get("lease_id"),
            filename=item.get("filename"),
            document_status=str(item.get("document_status", "signed")),
        )
        for item in lister()
    ]
    return StaticDocumentCatalog(metas)
