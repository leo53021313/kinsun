"""測試用關鍵字索引。"""

from __future__ import annotations

import re

from kinsun.rag.schemas import DocumentChunk, SearchResult

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class InMemoryKeywordIndex:
    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []

    def add(self, chunk: DocumentChunk) -> None:
        self._chunks.append(chunk)

    def search(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        query_terms = _tokenize(query)
        results: list[SearchResult] = []
        for chunk in self._chunks:
            searchable_text = f"{chunk.metadata.title} {chunk.metadata.topic} {chunk.text}"
            text_terms = set(_tokenize(searchable_text))
            matched = tuple(term for term in query_terms if term in text_terms)
            if not matched:
                continue
            score = len(matched) / max(len(query_terms), 1)
            results.append(SearchResult(chunk=chunk, score=score, matched_terms=matched))
        results.sort(key=lambda result: result.score, reverse=True)
        return tuple(results[:top_k])


def _tokenize(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    return tuple(match.group(0) for match in _TOKEN_RE.finditer(normalized))
