from datetime import datetime

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

    def log_ingestion(self, **kwargs):
        self.logs.append(kwargs)


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
