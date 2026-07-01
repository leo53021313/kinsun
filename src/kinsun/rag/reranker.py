"""檢索結果重排。"""

from __future__ import annotations

from datetime import date

from kinsun.rag.schemas import SearchResult, SourceType, TrustLevel

_TRUST_WEIGHT = {
    TrustLevel.HIGH: 1.0,
    TrustLevel.MEDIUM: 0.7,
    TrustLevel.LOW: 0.2,
}

_SOURCE_WEIGHT = {
    SourceType.GOVERNMENT: 1.0,
    SourceType.INTERNATIONAL_OFFICIAL: 0.95,
    SourceType.HOSPITAL: 0.9,
    SourceType.MEDICAL_ASSOCIATION: 0.9,
    SourceType.GUIDELINE: 0.95,
    SourceType.ACADEMIC: 0.85,
    SourceType.OTHER: 0.6,
}

_METHOD_WEIGHT = {
    "vector": 1.0,
    "keyword": 0.9,
}


def rerank(results: tuple[SearchResult, ...], *, top_k: int = 5) -> tuple[SearchResult, ...]:
    dedup: dict[str, SearchResult] = {}
    for result in results:
        chunk_id = result.chunk.metadata.chunk_id
        metadata = result.chunk.metadata
        weighted = SearchResult(
            chunk=result.chunk,
            score=(
                result.score
                * _TRUST_WEIGHT[metadata.trust_level]
                * _SOURCE_WEIGHT[metadata.source_type]
                * _METHOD_WEIGHT.get(result.retrieval_method, 0.85)
                * _freshness_weight(metadata.source_updated_at or metadata.source_published_at)
            ),
            matched_terms=result.matched_terms,
            retrieval_method=result.retrieval_method,
        )
        if chunk_id not in dedup or weighted.score > dedup[chunk_id].score:
            dedup[chunk_id] = weighted
    ordered = sorted(dedup.values(), key=lambda result: result.score, reverse=True)
    return tuple(ordered[:top_k])


def _freshness_weight(source_date: date | None) -> float:
    if source_date is None:
        return 0.85
    age_days = (date.today() - source_date).days
    if age_days <= 365:
        return 1.0
    if age_days <= 365 * 3:
        return 0.9
    return 0.75
