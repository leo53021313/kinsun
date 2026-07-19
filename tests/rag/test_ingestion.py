from datetime import datetime

import pytest

from kinsun.rag.embeddings import CharacterHashEmbedding
from kinsun.rag.ingestion import IngestionPipeline, SeedDocument
from kinsun.rag.source_registry import SourceRegistry


class _FakeStore:
    def __init__(self) -> None:
        self.sources = []
        self.documents = []
        self.chunks = []
        self.logs = []

    def upsert_source(self, source):
        self.sources.append(source)

    def upsert_document(self, document):
        self.documents.append(document)

    def add(self, chunk, vector):
        self.chunks.append((chunk, vector))

    def save_document(
        self,
        document,
        prepared_chunks,
        *,
        index_version,
        embedding_model_name,
        embedding_dimensions,
        fetched_at,
        parser_used,
        operator_or_job_id,
    ):
        self.documents.append(document)
        self.chunks.extend(prepared_chunks)
        self.logs.append(
            {
                "source_id": document.source_id,
                "document_id": document.document_id,
                "url": document.url,
                "fetched_at": fetched_at,
                "content_hash": document.content_hash,
                "chunk_count": len(prepared_chunks),
                "parser_used": parser_used,
                "status": "success",
                "error_message": None,
                "operator_or_job_id": operator_or_job_id,
                "index_version": index_version,
                "embedding_model_name": embedding_model_name,
                "embedding_dimensions": embedding_dimensions,
            }
        )

    def save_discovery_document(
        self,
        document,
        *,
        index_version,
        fetched_at,
        operator_or_job_id,
    ):
        self.documents.append(document)
        self.logs.append(
            {
                "source_id": document.source_id,
                "document_id": document.document_id,
                "url": document.url,
                "fetched_at": fetched_at,
                "content_hash": document.content_hash,
                "chunk_count": 0,
                "parser_used": "discovery",
                "status": "success",
                "error_message": None,
                "operator_or_job_id": operator_or_job_id,
                "index_version": index_version,
            }
        )

    def log_ingestion(self, **kwargs):
        self.logs.append(kwargs)


@pytest.mark.parametrize("max_chunk_chars", [79, 701])
def test_ingestion_rejects_chunk_limit_outside_80_to_700(max_chunk_chars):
    with pytest.raises(ValueError, match="80 到 700"):
        IngestionPipeline(
            store=_FakeStore(),
            embedding_model=CharacterHashEmbedding(dimensions=8),
            max_chunk_chars=max_chunk_chars,
        )


def test_ingestion_writes_source_document_chunks_and_audit_log():
    source = SourceRegistry().get("hpa_elder_health")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        max_chunk_chars=120,
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source_id=source.source_id,
                url="https://www.hpa.gov.tw/demo",
                title="高血壓衛教",
                publisher=source.publisher,
                text="長者高血壓照護可注意規律量血壓。\n均衡飲食與活動也很重要。",
                topic="高血壓",
            ),
        ),
        operator_or_job_id="test",
    )

    assert store.sources == [source]
    assert store.documents[0].title == "高血壓衛教"
    assert store.chunks[0][0].metadata.source_id == source.source_id
    assert len(store.chunks[0][1]) == 8
    assert store.logs[0]["status"] == "success"
    assert store.logs[0]["operator_or_job_id"] == "test"


def test_ingestion_deduplicates_url_and_content_with_audit_logs():
    source = SourceRegistry().get("hpa_elder_health")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source.source_id,
                "http://www.hpa.gov.tw/demo#old",
                "舊",
                "",
                "相同衛教。",
            ),
            SeedDocument(source.source_id, "https://www.hpa.gov.tw/demo", "新", "", "相同衛教。"),
        ),
        operator_or_job_id="dedupe-test",
    )

    assert len(store.documents) == 1
    assert store.documents[0].url == "https://www.hpa.gov.tw/demo"
    assert any(log["status"] == "skipped" for log in store.logs)


def test_same_url_and_timestamp_deduplication_is_order_independent():
    source = SourceRegistry().get("hpa_elder_health")

    def kept_text(seed_documents):
        store = _FakeStore()
        pipeline = IngestionPipeline(
            store=store,
            embedding_model=CharacterHashEmbedding(dimensions=8),
            clock=lambda: datetime(2026, 6, 30, 10, 0),
        )
        pipeline.ingest_seed_documents(
            source,
            seed_documents,
            operator_or_job_id="stable-dedupe-test",
        )
        return store.documents[0].text

    documents = (
        SeedDocument(source.source_id, "https://www.hpa.gov.tw/same", "甲", "", "版本甲。"),
        SeedDocument(source.source_id, "https://www.hpa.gov.tw/same", "乙", "", "版本乙。"),
    )

    assert kept_text(documents) == kept_text(tuple(reversed(documents)))


def test_ingestion_propagates_discovery_role_to_chunks():
    source = SourceRegistry().get("hpa_news_api")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    pipeline.ingest_seed_documents(
        source,
        (SeedDocument(source.source_id, source.url, "新聞", "", "健康新聞。"),),
        operator_or_job_id="role-test",
    )

    assert store.chunks[0][0].metadata.source_role.value == "discovery"


def test_versioned_discovery_document_is_audited_without_embedding():
    source = SourceRegistry().get("hpa_news_api")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    pipeline.ingest_seed_documents(
        source,
        (SeedDocument(source.source_id, source.url, "新聞", "", "健康新聞。"),),
        operator_or_job_id="role-test",
        index_version="rag-test",
    )

    assert len(store.documents) == 1
    assert store.chunks == []
    assert store.logs[0]["parser_used"] == "discovery"
