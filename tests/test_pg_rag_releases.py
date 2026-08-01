"""RAG release Postgres 整合測試；只連 KINSUN_TEST_DATABASE_URL。"""

import os
from datetime import datetime

import pytest

from kinsun.rag.embeddings import CharacterHashEmbedding
from kinsun.rag.ingestion import IngestionPipeline, SeedDocument
from kinsun.rag.releases import PgRagReleaseStore, RagReleaseError, ReleaseStatus
from kinsun.rag.schemas import RAG_EMBEDDING_DIMENSIONS, ContentPolicy
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.vector_store import PgVectorStore

pytestmark = pytest.mark.skipif(
    os.environ.get("KINSUN_IT") != "1",
    reason="需 KINSUN_IT=1（連獨立測試庫）",
)


@pytest.fixture(autouse=True)
def cleanup_release_rows(pg_database, ns):
    yield
    pg_database.execute(
        "DELETE FROM rag_index_releases WHERE index_version LIKE %s",
        (f"{ns}%",),
    )
    pg_database.execute(
        "DELETE FROM rag_ingestion_audit_logs WHERE operator_or_job_id LIKE %s",
        (f"{ns}%",),
    )
    pg_database.execute(
        "DELETE FROM rag_documents WHERE url LIKE %s",
        (f"%{ns}%",),
    )


class _NamedCharacterHashEmbedding(CharacterHashEmbedding):
    def __init__(self, model_name: str) -> None:
        super().__init__(dimensions=RAG_EMBEDDING_DIMENSIONS)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name


def _build_document(
    pg_database,
    *,
    version: str,
    text: str = "高血壓要規律量血壓。",
    model_name: str = "character-hash-test",
) -> str:
    source = SourceRegistry().get("hpa_health_education")
    pipeline = IngestionPipeline(
        store=PgVectorStore(pg_database),
        embedding_model=_NamedCharacterHashEmbedding(model_name),
        clock=lambda: datetime(2026, 7, 16, 12, 0),
    )
    documents = pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source.source_id,
                f"https://www.hpa.gov.tw/{version}",
                "高血壓衛教",
                source.publisher,
                text,
            ),
        ),
        operator_or_job_id=version,
        index_version=version,
    )
    return documents[0].document_id


def _begin(
    store: PgRagReleaseStore,
    version: str,
    *,
    model_name: str = "character-hash-test",
) -> None:
    store.begin_release(
        version,
        embedding_model=model_name,
        content_policy=ContentPolicy.ALLOWED_ONLY,
    )


def test_candidate_invisible_then_atomic_publish_and_rollback(pg_database, ns):
    releases = PgRagReleaseStore(pg_database)
    first = f"{ns}v1"
    second = f"{ns}v2"
    _begin(releases, first)
    _build_document(pg_database, version=first)
    query = CharacterHashEmbedding(dimensions=RAG_EMBEDDING_DIMENSIONS).embed_query("高血壓")
    assert PgVectorStore(pg_database).search(query) == ()

    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (first,),
    )
    releases.publish(first)
    assert PgVectorStore(pg_database).search(query)

    _begin(releases, second)
    _build_document(pg_database, version=second, text="糖尿病要規律量血糖。")
    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (second,),
    )
    releases.publish(second)
    assert releases.get_active().index_version == second

    releases.rollback(first)
    assert releases.get_active().index_version == first


def test_failed_release_keeps_active_and_only_one_building_allowed(pg_database, ns):
    releases = PgRagReleaseStore(pg_database)
    active = f"{ns}active"
    failed = f"{ns}failed"
    blocked = f"{ns}blocked"
    _begin(releases, active)
    _build_document(pg_database, version=active)
    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (active,),
    )
    releases.publish(active)

    _begin(releases, failed)
    with pytest.raises(RagReleaseError):
        _begin(releases, blocked)
    releases.mark_failed(failed, error_message="quality gate failed")

    assert releases.get_active().index_version == active
    assert releases.get(failed).status == ReleaseStatus.FAILED


def test_unchanged_document_reuses_compatible_chunks(pg_database, ns):
    releases = PgRagReleaseStore(pg_database)
    first = f"{ns}reuse1"
    second = f"{ns}reuse2"
    _begin(releases, first)
    document_id = _build_document(pg_database, version=first)
    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (first,),
    )
    releases.publish(first)
    _begin(releases, second)

    source = SourceRegistry().get("hpa_health_education")
    row = pg_database.query_one(
        "SELECT source_id, url, title, publisher, text, content_hash, source_type, language, "
        "topic, audience, medical_scope, trust_level, copyright_status, published_at, "
        "updated_at, retrieved_at FROM rag_documents WHERE document_id=%s",
        (document_id,),
    )
    from kinsun.rag.migrate import _row_to_document

    reused = PgVectorStore(pg_database).reuse_document(
        _row_to_document((document_id, *row)),
        source_role=source.role,
        index_version=second,
        fetched_at=1.0,
        operator_or_job_id=second,
    )

    assert reused is True
    membership = pg_database.query_one(
        "SELECT 1 FROM rag_release_documents WHERE index_version=%s AND document_id=%s",
        (second, document_id),
    )
    assert membership == (1,)
    reused_chunks = pg_database.query_one(
        "SELECT COUNT(*) FROM rag_release_chunks WHERE index_version=%s",
        (second,),
    )
    assert reused_chunks[0] > 0


def test_new_embedding_model_does_not_mutate_active_chunks(pg_database, ns):
    releases = PgRagReleaseStore(pg_database)
    first = f"{ns}model1"
    second = f"{ns}model2"
    _begin(releases, first, model_name="embedding-a")
    _build_document(pg_database, version=first, model_name="embedding-a")
    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (first,),
    )
    releases.publish(first)
    first_chunk = pg_database.query_one(
        "SELECT chunk_id FROM rag_release_chunks WHERE index_version=%s ORDER BY chunk_id LIMIT 1",
        (first,),
    )[0]

    _begin(releases, second, model_name="embedding-b")
    _build_document(pg_database, version=second, model_name="embedding-b")
    still_active_chunk = pg_database.query_one(
        """
        SELECT rc.chunk_id
        FROM rag_release_chunks rc
        JOIN rag_index_releases r ON r.index_version=rc.index_version
        WHERE r.status='active' ORDER BY rc.chunk_id LIMIT 1
        """
    )[0]
    second_chunk = pg_database.query_one(
        "SELECT chunk_id FROM rag_release_chunks WHERE index_version=%s ORDER BY chunk_id LIMIT 1",
        (second,),
    )[0]

    assert still_active_chunk == first_chunk
    assert second_chunk != first_chunk


def test_discovery_document_has_membership_without_embedding_or_orphan(pg_database, ns):
    version = f"{ns}discovery"
    releases = PgRagReleaseStore(pg_database)
    _begin(releases, version)
    source = SourceRegistry().get("hpa_news_api")
    pipeline = IngestionPipeline(
        store=PgVectorStore(pg_database),
        embedding_model=CharacterHashEmbedding(dimensions=RAG_EMBEDDING_DIMENSIONS),
    )

    pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source.source_id,
                f"https://www.hpa.gov.tw/{version}",
                "更新發現紀錄",
                source.publisher,
                "此內容只供發現與稽核。",
            ),
        ),
        operator_or_job_id=version,
        index_version=version,
    )

    metrics = releases.structural_metrics(version)
    assert metrics["document_count"] == 1
    assert metrics["chunk_count"] == 0
    assert metrics["orphan_document_count"] == 0


def test_structural_metrics_do_not_misclassify_multiple_documents_as_orphans(pg_database, ns):
    version = f"{ns}multiple-documents"
    releases = PgRagReleaseStore(pg_database)
    _begin(releases, version)
    _build_document(pg_database, version=version, text="高血壓要規律量血壓。")
    _build_document(pg_database, version=version, text="糖尿病要規律量血糖。")

    metrics = releases.structural_metrics(version)

    assert metrics["document_count"] == 2
    assert metrics["chunk_count"] == 2
    assert metrics["orphan_document_count"] == 0
    assert metrics["orphan_chunk_count"] == 0


def test_failed_release_atomic_document_can_be_reused(pg_database, ns):
    failed = f"{ns}failed-reuse"
    resumed = f"{ns}resumed"
    releases = PgRagReleaseStore(pg_database)
    _begin(releases, failed)
    document_id = _build_document(pg_database, version=failed)
    releases.mark_failed(failed, error_message="外部服務逾時")
    _begin(releases, resumed)

    source = SourceRegistry().get("hpa_health_education")
    row = pg_database.query_one(
        "SELECT source_id, url, title, publisher, text, content_hash, source_type, language, "
        "topic, audience, medical_scope, trust_level, copyright_status, published_at, "
        "updated_at, retrieved_at FROM rag_documents WHERE document_id=%s",
        (document_id,),
    )
    from kinsun.rag.migrate import _row_to_document

    reused = PgVectorStore(pg_database).reuse_document(
        _row_to_document((document_id, *row)),
        source_role=source.role,
        index_version=resumed,
        fetched_at=1.0,
        operator_or_job_id=resumed,
    )

    assert reused is True
    assert releases.structural_metrics(resumed)["chunk_count"] > 0


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需要 KINSUN_IT=1 與測試資料庫")
def test_ensure_schema_upgrades_existing_768_dimension_column():
    """既有庫的向量欄位維度要能升級。

    `CREATE TABLE IF NOT EXISTS` 不會改既有表——空測試庫跑得過，正式庫卻不會升級。
    2026-08-01 把 RAG 從 Gemini（768 維）換成 BGE-M3（1024 維）時就靠這條守住。
    """
    from kinsun.db import connect, ensure_schema

    url = os.environ["KINSUN_TEST_DATABASE_URL"]
    ensure_schema(url)
    with connect(url) as conn:
        # 先把欄位退回舊維度，模擬「已經跑過舊版的正式庫」
        conn.execute("DROP INDEX IF EXISTS idx_rag_chunks_embedding")
        conn.execute("ALTER TABLE rag_chunks DROP COLUMN IF EXISTS embedding")
        conn.execute("ALTER TABLE rag_chunks ADD COLUMN embedding vector(768)")

    ensure_schema(url)

    with connect(url) as conn:
        dimensions = conn.execute(
            """
            SELECT a.atttypmod FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'rag_chunks' AND a.attname = 'embedding'
            """
        ).fetchone()[0]
        has_index = conn.execute(
            "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_rag_chunks_embedding'"
        ).fetchone()[0]

    assert dimensions == RAG_EMBEDDING_DIMENSIONS
    assert has_index == 1, "維度升級後 HNSW 索引必須重建"
