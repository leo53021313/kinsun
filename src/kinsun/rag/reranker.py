"""檢索結果重排。"""

from __future__ import annotations

from kinsun.rag.schemas import SearchResult, TrustLevel

_TRUST_WEIGHT = {
    TrustLevel.HIGH: 1.0,
    TrustLevel.MEDIUM: 0.7,
    TrustLevel.LOW: 0.2,
}


def rerank(results: tuple[SearchResult, ...], *, top_k: int = 5) -> tuple[SearchResult, ...]:
    dedup: dict[str, SearchResult] = {}
    for result in results:
        chunk_id = result.chunk.metadata.chunk_id
        weighted = SearchResult(
            chunk=result.chunk,
            score=result.score * _TRUST_WEIGHT[result.chunk.metadata.trust_level],
            matched_terms=result.matched_terms,
        )
        if chunk_id not in dedup or weighted.score > dedup[chunk_id].score:
            dedup[chunk_id] = weighted
    ordered = sorted(dedup.values(), key=lambda result: result.score, reverse=True)
    return tuple(ordered[:top_k])
