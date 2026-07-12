"""Citation 組裝：同 chunk 去重、欄位映射。"""

from __future__ import annotations

from datetime import date

from kinsun.rag.citation import assemble_citations
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


def _result(chunk_id: str) -> SearchResult:
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
        source_published_at=date(2026, 1, 1),
        source_updated_at=None,
        retrieved_at=date(2026, 6, 30),
    )
    return SearchResult(chunk=DocumentChunk(text="內容", metadata=metadata), score=0.9)


def test_maps_metadata_fields():
    (citation,) = assemble_citations((_result("doc-1#chunk-1"),))
    assert citation.source_id == "hpa_elder_health"
    assert citation.title == "高血壓衛教"
    assert citation.publisher == "衛生福利部國民健康署"
    assert citation.url == "https://www.hpa.gov.tw/demo"
    assert citation.chunk_id == "doc-1#chunk-1"


def test_duplicate_chunks_cited_once():
    citations = assemble_citations(
        (_result("doc-1#chunk-1"), _result("doc-1#chunk-1"), _result("doc-1#chunk-2"))
    )
    assert [c.chunk_id for c in citations] == ["doc-1#chunk-1", "doc-1#chunk-2"]
