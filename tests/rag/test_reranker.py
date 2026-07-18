"""重排權重：新鮮度分段、去重取高分、top_k 截斷。"""

from __future__ import annotations

from datetime import date, timedelta

from kinsun.rag.reranker import rerank
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    SearchResult,
    SourceType,
    TrustLevel,
)


def _result(
    chunk_id: str,
    *,
    score: float = 1.0,
    updated_at: date | None = None,
    method: str = "vector",
) -> SearchResult:
    metadata = ChunkMetadata(
        source_id="hpa_elder_health",
        document_id="doc-1",
        chunk_id=chunk_id,
        title="高血壓衛教",
        publisher="衛生福利部國民健康署",
        source_url="https://www.hpa.gov.tw/demo",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic="高血壓",
        audience=Audience.ELDER,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        approved_for_rag=True,
        copyright_status=CopyrightStatus.ALLOWED,
        source_published_at=None,
        source_updated_at=updated_at,
        retrieved_at=date(2026, 6, 30),
    )
    return SearchResult(
        chunk=DocumentChunk(text="內容", metadata=metadata),
        score=score,
        retrieval_method=method,
    )


def _score_of(results: tuple[SearchResult, ...], chunk_id: str) -> float:
    return next(r.score for r in results if r.chunk.metadata.chunk_id == chunk_id)


def test_freshness_weight_tiers():
    today = date.today()
    ranked = rerank(
        (
            _result("c-fresh", updated_at=today - timedelta(days=30)),  # ≤1 年 → 1.0
            _result("c-2y", updated_at=today - timedelta(days=730)),  # ≤3 年 → 0.9
            _result("c-5y", updated_at=today - timedelta(days=1825)),  # >3 年 → 0.75
            _result("c-undated", updated_at=None),  # 無日期 → 0.85
        )
    )
    assert _score_of(ranked, "c-fresh") == 1.0
    assert _score_of(ranked, "c-2y") == 0.9
    assert _score_of(ranked, "c-5y") == 0.75
    assert _score_of(ranked, "c-undated") == 0.85
    # 排序依加權分數由高到低。
    assert [r.chunk.metadata.chunk_id for r in ranked] == ["c-fresh", "c-2y", "c-undated", "c-5y"]


def test_dedup_keeps_higher_weighted_score():
    today = date.today()
    ranked = rerank(
        (
            _result("c-1", score=0.5, updated_at=today),
            _result("c-1", score=0.9, updated_at=today),
        )
    )
    assert len(ranked) == 1
    assert ranked[0].score == 0.9


def test_top_k_truncates():
    today = date.today()
    results = tuple(_result(f"c-{i}", score=1.0 - i * 0.1, updated_at=today) for i in range(5))
    assert len(rerank(results, top_k=2)) == 2


def test_unknown_retrieval_method_gets_conservative_weight():
    today = date.today()
    ranked = rerank((_result("c-1", updated_at=today, method="mystery"),))
    assert ranked[0].score == 0.85


def test_keyword_and_vector_methods_use_equal_base_weight():
    today = date.today()
    ranked = rerank(
        (
            _result("vector", updated_at=today, method="vector"),
            _result("keyword", updated_at=today, method="keyword"),
        )
    )

    assert _score_of(ranked, "vector") == 1.0
    assert _score_of(ranked, "keyword") == 1.0
