"""极简 BM25 检索（Task 011）。

为什么先不接向量库：
- P0 只需要"能定位到章节并给出分数"的最小可评测路径；
- BM25 完全确定性、零外部服务，便于在测试中冻结结果；
- 若后续评测显示召回不足，再引入向量/混合检索（路线图 P1）。

分词：中文按二元组、英文/数字按词，避免引入分词依赖。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

__all__ = ["BM25Index", "tokenize"]

#: 中文只取二元组（单字仅在整段只有一个字时保留）：
#: 单字召回会把"押金"这类无关查询匹配到任意含"金/押"的条款上，噪声大于收益。
_TOKEN = re.compile(r"[A-Za-z0-9_.]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    chinese_run: list[str] = []

    def flush_chinese() -> None:
        if not chinese_run:
            return
        if len(chinese_run) == 1:
            tokens.append(chinese_run[0])
        else:
            tokens.extend(
                chinese_run[i] + chinese_run[i + 1] for i in range(len(chinese_run) - 1)
            )
        chinese_run.clear()

    for match in _TOKEN.finditer(text):
        item = match.group(0)
        if "\u4e00" <= item <= "\u9fff":
            chinese_run.append(item)
        else:
            flush_chinese()
            tokens.append(item.lower())
    flush_chinese()
    return tokens


@dataclass(frozen=True)
class _Doc:
    doc_id: str
    tokens: Counter
    length: int


class BM25Index:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._docs: dict[str, _Doc] = {}
        self._df: Counter = Counter()
        self._total_length = 0

    def __len__(self) -> int:
        return len(self._docs)

    def add(self, doc_id: str, text: str) -> None:
        tokens = Counter(tokenize(text))
        if doc_id in self._docs:
            self.remove(doc_id)
        self._docs[doc_id] = _Doc(doc_id=doc_id, tokens=tokens, length=sum(tokens.values()))
        self._total_length += sum(tokens.values())
        for token in tokens:
            self._df[token] += 1

    def remove(self, doc_id: str) -> None:
        doc = self._docs.pop(doc_id, None)
        if doc is None:
            return
        self._total_length -= doc.length
        for token in doc.tokens:
            self._df[token] -= 1
            if self._df[token] <= 0:
                del self._df[token]

    def search(self, query: str, *, top_k: int = 5) -> list[tuple[str, float]]:
        if not self._docs:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        total_docs = len(self._docs)
        avg_length = self._total_length / total_docs if total_docs else 0.0
        scored: list[tuple[str, float]] = []
        for doc in self._docs.values():
            score = 0.0
            for token in query_tokens:
                frequency = doc.tokens.get(token, 0)
                if not frequency:
                    continue
                df = self._df.get(token, 0)
                if not df:
                    continue
                idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                denominator = frequency + self._k1 * (
                    1 - self._b + self._b * (doc.length / avg_length if avg_length else 1)
                )
                score += idf * (frequency * (self._k1 + 1)) / denominator
            if score > 0:
                scored.append((doc.doc_id, round(score, 6)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]