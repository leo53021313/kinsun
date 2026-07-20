from datetime import date

from kinsun.rag.retriever import extract_keyword_terms
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    RagDocument,
    SourceType,
    TrustLevel,
)
from kinsun.rag.vector_store import (
    PgVectorStore,
    _release_chunk_variant,
    _remap_chunk_document,
)


class _FakeDb:
    def __init__(self, rows=None) -> None:
        self.calls = []
        self._rows = rows or []

    def execute(self, sql, params=()):
        self.calls.append(("execute", sql, params))

    def query(self, sql, params=()):
        self.calls.append(("query", sql, params))
        return self._rows

    def query_one(self, sql, params=()):
        return None


def _chunk() -> DocumentChunk:
    metadata = ChunkMetadata(
        source_id="hpa",
        document_id="doc",
        chunk_id="doc#chunk-1",
        title="高血壓衛教",
        publisher="衛生福利部國民健康署",
        source_url="https://example.test",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic="高血壓",
        audience=Audience.ELDER,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        approved_for_rag=True,
        copyright_status=CopyrightStatus.ALLOWED,
        source_published_at=date(2026, 1, 1),
        source_updated_at=date(2026, 1, 1),
        retrieved_at=date(2026, 6, 30),
    )
    return DocumentChunk(text="規律量血壓。", metadata=metadata)


def _document(document_id: str) -> RagDocument:
    return RagDocument(
        document_id=document_id,
        source_id="hpa",
        url=f"https://example.test/{document_id}",
        title="高血壓衛教",
        publisher="衛生福利部國民健康署",
        text="規律量血壓。",
        content_hash=f"hash-{document_id}",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic="高血壓",
        audience=Audience.ELDER,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        copyright_status=CopyrightStatus.ALLOWED,
        published_at=None,
        updated_at=None,
        retrieved_at=date(2026, 6, 30),
    )


def test_pg_vector_store_add_casts_embedding_to_vector_literal():
    db = _FakeDb()
    PgVectorStore(db).add(_chunk(), (0.1, 0.2))

    params = db.calls[0][2]
    assert params[4] == "[0.1,0.2]"
    assert "embedding_model" in db.calls[0][1]


def test_release_chunk_variant_is_stable_and_model_specific():
    first = _release_chunk_variant(_chunk(), "embedding-a")
    same = _release_chunk_variant(_chunk(), "embedding-a")
    other = _release_chunk_variant(_chunk(), "embedding-b")

    assert first.metadata.chunk_id == same.metadata.chunk_id
    assert first.metadata.chunk_id != other.metadata.chunk_id
    assert first.text == _chunk().text


def test_chunk_can_be_remapped_to_legacy_document_id_without_losing_suffix():
    remapped = _remap_chunk_document(_chunk(), "legacy-doc")

    assert remapped.metadata.document_id == "legacy-doc"
    assert remapped.metadata.chunk_id == "legacy-doc#chunk-1"


def test_pg_vector_store_search_maps_rows_to_results():
    row = (
        "doc#chunk-1",
        "doc",
        "hpa",
        "規律量血壓。",
        "高血壓衛教",
        "衛生福利部國民健康署",
        "https://example.test",
        "government",
        "zh-TW",
        "高血壓",
        "elder",
        "health_education",
        "high",
        True,
        "allowed",
        date(2026, 1, 1),
        date(2026, 1, 1),
        date(2026, 6, 30),
        date(2026, 6, 30),
        None,
        "answer",
        0.8,
    )
    result = PgVectorStore(_FakeDb(rows=[row])).search((0.1, 0.2))[0]

    assert result.chunk.metadata.chunk_id == "doc#chunk-1"
    assert result.retrieval_method == "vector"
    assert result.score == 0.8


def test_pg_vector_store_search_uses_release_chunk_membership():
    db = _FakeDb()

    PgVectorStore(db).search((0.1, 0.2))

    assert "JOIN rag_release_chunks" in db.calls[0][1]


def test_pg_keyword_score_is_normalized_to_zero_one_scale():
    db = _FakeDb()
    query = "高血壓"

    PgVectorStore(db).keyword_search(query)

    terms = extract_keyword_terms(query)
    params = db.calls[0][2]
    assert params[len(terms) * 3] == len(terms) * 5
    assert "/ %s AS score" in db.calls[0][1]


def test_skipped_document_audits_are_batched_into_one_insert():
    db = _FakeDb()

    PgVectorStore(db).log_skipped_documents(
        ((_document("doc-1"), "duplicate"), (_document("doc-2"), "duplicate")),
        fetched_at=1.0,
        parser_used="deduplication",
        operator_or_job_id="release-1",
    )

    assert len(db.calls) == 1
    assert "rag_ingestion_audit_logs" in db.calls[0][1]
    assert len(db.calls[0][2]) == 20
