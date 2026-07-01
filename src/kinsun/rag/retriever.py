"""衛教 RAG 檢索器。"""

from __future__ import annotations

import re

from kinsun.rag.embeddings import QueryEmbeddingModel
from kinsun.rag.keyword_index import InMemoryKeywordIndex
from kinsun.rag.reranker import rerank
from kinsun.rag.schemas import SearchResult

_KEYWORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")

_SYNONYMS = {
    "血壓高": "高血壓",
    "三高": "高血壓 高血糖 高血脂",
    "老人": "長者",
    "阿公": "長者",
    "阿嬤": "長者",
    "睡不著": "睡眠",
    "袂睏": "睡眠",
    "睏袂去": "睡眠",
}


class HealthEducationRetriever:
    def __init__(
        self,
        keyword_index: InMemoryKeywordIndex | None = None,
        *,
        vector_store=None,
        embedding_model: QueryEmbeddingModel | None = None,
    ) -> None:
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._embedding_model = embedding_model

    def retrieve(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        normalized = normalize_query(query)
        results: list[SearchResult] = []
        if self._vector_store is not None and self._embedding_model is not None:
            query_vector = self._embedding_model.embed_query(normalized)
            results.extend(self._vector_store.search(query_vector, top_k=top_k * 3))
        if self._keyword_index is not None:
            results.extend(self._keyword_index.search(normalized, top_k=top_k * 3))
        elif self._vector_store is not None:
            results.extend(self._vector_store.keyword_search(normalized, top_k=top_k * 3))
        filtered = tuple(result for result in results if _is_allowed_chunk(result))
        return rerank(filtered, top_k=top_k)


def normalize_query(query: str) -> str:
    normalized = query.strip()
    for source, target in _SYNONYMS.items():
        normalized = normalized.replace(source, f"{source} {target}")
    return normalized


def extract_keyword_terms(query: str) -> tuple[str, ...]:
    normalized = normalize_query(query).lower()
    terms = []
    seen = set()
    for match in _KEYWORD_RE.finditer(normalized):
        term = match.group(0)
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)


def _is_allowed_chunk(result: SearchResult) -> bool:
    metadata = result.chunk.metadata
    return metadata.approved_for_rag
