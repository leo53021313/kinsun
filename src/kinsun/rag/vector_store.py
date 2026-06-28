"""向量儲存介面與 in-memory 測試實作。"""

from __future__ import annotations

from kinsun.rag.schemas import DocumentChunk, SearchResult


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._entries: list[tuple[DocumentChunk, tuple[float, ...]]] = []

    def add(self, chunk: DocumentChunk, vector: tuple[float, ...]) -> None:
        self._entries.append((chunk, vector))

    def search(
        self,
        query_vector: tuple[float, ...],
        *,
        top_k: int = 5,
    ) -> tuple[SearchResult, ...]:
        scored = [
            SearchResult(chunk=chunk, score=_cosine(query_vector, vector))
            for chunk, vector in self._entries
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return tuple(scored[:top_k])


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("向量維度不一致")
    return sum(l_value * r_value for l_value, r_value in zip(left, right, strict=True))
