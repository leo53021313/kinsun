"""衛教 RAG 檢索器。"""

from __future__ import annotations

from kinsun.rag.keyword_index import InMemoryKeywordIndex
from kinsun.rag.reranker import rerank
from kinsun.rag.schemas import CopyrightStatus, SearchResult

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
    def __init__(self, keyword_index: InMemoryKeywordIndex) -> None:
        self._keyword_index = keyword_index

    def retrieve(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        normalized = normalize_query(query)
        keyword_results = self._keyword_index.search(normalized, top_k=top_k * 2)
        filtered = tuple(result for result in keyword_results if _is_allowed_chunk(result))
        return rerank(filtered, top_k=top_k)


def normalize_query(query: str) -> str:
    normalized = query.strip()
    for source, target in _SYNONYMS.items():
        normalized = normalized.replace(source, f"{source} {target}")
    return normalized


def _is_allowed_chunk(result: SearchResult) -> bool:
    metadata = result.chunk.metadata
    return metadata.approved_for_rag and metadata.copyright_status == CopyrightStatus.ALLOWED
