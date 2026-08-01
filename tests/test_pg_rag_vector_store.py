"""PgVectorStore 真庫整合測試（✅ D-34 丙-4 補）。

需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`（獨立測試庫，含 pgvector）。
驗證 add→search 在真 Postgres／pgvector 上跑通：向量字面值轉型、
維度、JOIN 與相似度排序皆非 Fake 可代驗。
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from kinsun.rag.releases import PgRagReleaseStore
from kinsun.rag.schemas import (
    RAG_EMBEDDING_DIMENSIONS,
    Audience,
    ChunkMetadata,
    ContentPolicy,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    RagDocument,
    RecommendedStatus,
    Source,
    SourceType,
    TrustLevel,
)
from kinsun.rag.vector_store import PgVectorStore

pytestmark = pytest.mark.skipif(
    os.environ.get("KINSUN_IT") != "1", reason="需 KINSUN_IT=1（連獨立測試庫）"
)

_DIM = RAG_EMBEDDING_DIMENSIONS


@pytest.fixture(autouse=True)
def cleanup_vector_rows(pg_database, ns):
    yield
    pg_database.execute(
        "DELETE FROM rag_index_releases WHERE index_version LIKE %s",
        (f"{ns}%",),
    )
    pg_database.execute(
        "DELETE FROM rag_documents WHERE document_id LIKE %s",
        (f"{ns}%",),
    )
    pg_database.execute(
        "DELETE FROM rag_sources WHERE source_id LIKE %s",
        (f"{ns}%",),
    )


def _chunk(ns: str, text: str, index: int) -> DocumentChunk:
    metadata = ChunkMetadata(
        source_id=f"{ns}hpa",
        document_id=f"{ns}doc",
        chunk_id=f"{ns}doc#chunk-{index}",
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
    return DocumentChunk(text=text, metadata=metadata)


def _vector(head: float) -> tuple[float, ...]:
    return (head,) + (0.0,) * (_DIM - 1)


def _seed_source_and_document(store: PgVectorStore, ns: str) -> None:
    """chunk 有 FK 約束：先建 source 與 document 才能入庫。"""
    store.upsert_source(
        Source(
            source_id=f"{ns}hpa",
            title="高血壓衛教",
            url="https://example.test",
            publisher="衛生福利部國民健康署",
            source_type=SourceType.GOVERNMENT,
            trust_level=TrustLevel.HIGH,
            copyright_status=CopyrightStatus.ALLOWED,
            recommended_status=RecommendedStatus.APPROVED,
            approved_for_rag=True,
        )
    )
    store.upsert_document(
        RagDocument(
            document_id=f"{ns}doc",
            source_id=f"{ns}hpa",
            url="https://example.test",
            title="高血壓衛教",
            publisher="衛生福利部國民健康署",
            text="全文",
            content_hash=f"{ns}hash",
            source_type=SourceType.GOVERNMENT,
            language=Language.ZH_TW,
            topic="高血壓",
            audience=Audience.ELDER,
            medical_scope=MedicalScope.HEALTH_EDUCATION,
            trust_level=TrustLevel.HIGH,
            copyright_status=CopyrightStatus.ALLOWED,
            published_at=date(2026, 1, 1),
            updated_at=date(2026, 1, 1),
            retrieved_at=date(2026, 6, 30),
        )
    )


def test_add_then_search_returns_most_similar_first(pg_database, ns):
    index_version = f"{ns}v1"
    embedding_model = "pgvector-test"
    releases = PgRagReleaseStore(pg_database)
    releases.begin_release(
        index_version,
        embedding_model=embedding_model,
        content_policy=ContentPolicy.ALLOWED_ONLY,
    )
    store = PgVectorStore(pg_database, embedding_model=embedding_model)
    _seed_source_and_document(store, ns)
    chunks = (_chunk(ns, "規律量血壓。", 1), _chunk(ns, "少鹽少油。", 2))
    store.add(chunks[0], _vector(1.0))
    store.add(chunks[1], _vector(-1.0))
    pg_database.execute(
        "INSERT INTO rag_release_documents (index_version, document_id) VALUES (%s,%s)",
        (index_version, f"{ns}doc"),
    )
    for chunk in chunks:
        pg_database.execute(
            "INSERT INTO rag_release_chunks (index_version, chunk_id) VALUES (%s,%s)",
            (index_version, chunk.metadata.chunk_id),
        )
    pg_database.execute(
        "UPDATE rag_index_releases SET status='candidate' WHERE index_version=%s",
        (index_version,),
    )
    releases.publish(index_version)

    results = PgVectorStore(pg_database).search(_vector(1.0), top_k=2)
    texts = [r.chunk.text for r in results if r.chunk.metadata.chunk_id.startswith(ns)]
    assert texts and texts[0] == "規律量血壓。"
