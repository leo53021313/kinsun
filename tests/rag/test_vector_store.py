from datetime import date

from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    SourceType,
    TrustLevel,
)
from kinsun.rag.vector_store import PgVectorStore


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


def test_pg_vector_store_add_casts_embedding_to_vector_literal():
    db = _FakeDb()
    PgVectorStore(db).add(_chunk(), (0.1, 0.2))

    params = db.calls[0][2]
    assert params[4] == "[0.1,0.2]"


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
        0.8,
    )
    result = PgVectorStore(_FakeDb(rows=[row])).search((0.1, 0.2))[0]

    assert result.chunk.metadata.chunk_id == "doc#chunk-1"
    assert result.retrieval_method == "vector"
    assert result.score == 0.8
