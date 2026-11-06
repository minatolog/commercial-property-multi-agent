"""PDF 文本提取与条款级分块（Task 011）。

分块策略：**按页提取 → 按条款编号切分 → 保留页码**。
不跨页合并条款，因为证据必须能定位到"第几页第几条"，跨页会破坏可追溯性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Chunk", "chunk_pages", "extract_pages"]

_CLAUSE = re.compile(r"^(第[一二三四五六七八九十百]+条|\d+\.\d+|附件[A-Z]?|附[件录])")

#: 页脚形如 "第 2 页 / 共 3 页"，不能混进条款正文，否则会污染证据摘录。
_PAGE_FOOTER = re.compile(r"^第\s*\d+\s*页\s*(?:/|／)?\s*(?:共\s*\d+\s*页)?$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    document_version: int
    page: int
    clause_id: str
    text: str
    synthetic: bool = True


def extract_pages(pdf_path: str | Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def chunk_pages(
    pages: list[str], *, document_id: str, document_version: int = 1
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, text in enumerate(pages, start=1):
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not _PAGE_FOOTER.match(line.strip())
        ]
        current_clause: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer, current_clause
            if current_clause and buffer:
                body = "\n".join(buffer)
                chunks.append(
                    Chunk(
                        chunk_id=f"{document_id}#v{document_version}#p{page_number}#{current_clause}",
                        document_id=document_id,
                        document_version=document_version,
                        page=page_number,
                        clause_id=current_clause,
                        text=body,
                    )
                )
            buffer = []

        for line in lines:
            if _CLAUSE.match(line):
                flush()
                current_clause = _clause_key(line)
                buffer = [line]
            elif current_clause is not None:
                buffer.append(line)
        flush()
    return chunks


def _clause_key(line: str) -> str:
    if line.startswith("附件"):
        return "附件B" if "B" in line else "附件"
    if line.startswith("附"):
        return "附件"
    match = re.match(r"^(\d+(?:\.\d+)+)", line)
    if match:
        return match.group(1)
    match = re.match(r"^(第[一二三四五六七八九十百]+条)", line)
    if match:
        return match.group(1)
    return line[:12]