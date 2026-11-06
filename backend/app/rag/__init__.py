"""合同知识层（Task 011）：PDF 生成/解析、分块、检索与引用验证。

`pdf_builder` 需要 reportlab，属于"离线生成工具"而非运行期依赖，
因此不在包初始化时导入（否则 `python -m app.rag.pdf_builder` 会触发重复导入告警）。
"""

from .chunker import Chunk, chunk_pages, extract_pages
from .service import CitationCheck, DocumentIndex, KnowledgeService, RetrievedChunk

__all__ = [
    "Chunk",
    "CitationCheck",
    "DocumentIndex",
    "KnowledgeService",
    "RetrievedChunk",
    "chunk_pages",
    "extract_pages",
]
