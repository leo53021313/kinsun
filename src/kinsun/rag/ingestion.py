"""衛教 RAG ingestion pipeline：文件 → chunk → embedding → vector store。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from kinsun.rag.chunker import chunk_text
from kinsun.rag.crawler import ParsedPage
from kinsun.rag.embeddings import EmbeddingError, QueryEmbeddingModel
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CrawlStatus,
    Language,
    MedicalScope,
    RagDocument,
    Source,
)

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_TOPIC_HINTS = {
    "高血壓": ("高血壓", "血壓", "三高"),
    "糖尿病": ("糖尿病", "血糖"),
    "高血脂": ("高血脂", "血脂", "膽固醇"),
    "睡眠": ("睡眠", "失眠", "睡不著", "袂睏"),
    "運動": ("運動", "活動", "肌力"),
    "飲食": ("飲食", "營養", "蔬果", "鹽"),
    "疫苗": ("疫苗", "接種"),
    "用藥安全": ("用藥", "藥物", "藥品"),
    "預防保健": ("預防", "篩檢", "健康檢查"),
}


class RagWriteStore(Protocol):
    def upsert_source(self, source: Source) -> None: ...
    def upsert_document(self, document: RagDocument) -> None: ...
    def add(self, chunk, vector: tuple[float, ...]) -> None: ...
    def log_ingestion(
        self,
        *,
        source_id: str,
        fetched_at: float,
        content_hash: str,
        chunk_count: int,
        parser_used: str,
        status: str,
        error_message: str | None,
        operator_or_job_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class SeedDocument:
    source_id: str
    url: str
    title: str
    publisher: str
    text: str
    topic: str = "一般衛教"
    language: Language = Language.ZH_TW
    audience: Audience = Audience.GENERAL_PUBLIC
    medical_scope: MedicalScope = MedicalScope.HEALTH_EDUCATION
    published_at: date | None = None
    updated_at: date | None = None


class IngestionPipeline:
    def __init__(
        self,
        *,
        store: RagWriteStore,
        embedding_model: QueryEmbeddingModel,
        max_chunk_chars: int = 700,
        clock=lambda: datetime.now(),
    ) -> None:
        self._store = store
        self._embedding_model = embedding_model
        self._max_chunk_chars = max_chunk_chars
        self._clock = clock

    def ingest_seed_documents(
        self,
        source: Source,
        documents: tuple[SeedDocument, ...],
        *,
        operator_or_job_id: str,
    ) -> tuple[RagDocument, ...]:
        rag_documents = tuple(
            _seed_to_document(source, doc, self._clock().date()) for doc in documents
        )
        self.ingest_documents(source, rag_documents, operator_or_job_id=operator_or_job_id)
        return rag_documents

    def ingest_pages(
        self,
        source: Source,
        pages: tuple[ParsedPage, ...],
        *,
        operator_or_job_id: str,
    ) -> tuple[RagDocument, ...]:
        documents = tuple(_page_to_document(source, page, self._clock().date()) for page in pages)
        self.ingest_documents(source, documents, operator_or_job_id=operator_or_job_id)
        return documents

    def ingest_documents(
        self,
        source: Source,
        documents: tuple[RagDocument, ...],
        *,
        operator_or_job_id: str,
    ) -> None:
        self._store.upsert_source(source)
        for document in documents:
            try:
                self._store.upsert_document(document)
                chunks = chunk_text(
                    document.text,
                    _metadata_for(document, source),
                    max_chars=self._max_chunk_chars,
                )
                for chunk in chunks:
                    vector = self._embedding_model.embed_document(
                        chunk.text,
                        title=chunk.metadata.title,
                    )
                    self._store.add(chunk, vector)
                self._store.log_ingestion(
                    source_id=source.source_id,
                    fetched_at=self._clock().timestamp(),
                    content_hash=document.content_hash,
                    chunk_count=len(chunks),
                    parser_used="ingestion",
                    status=CrawlStatus.SUCCESS.value,
                    error_message=None,
                    operator_or_job_id=operator_or_job_id,
                )
            except (EmbeddingError, Exception) as exc:  # noqa: BLE001 - 單篇失敗不中斷整批
                self._store.log_ingestion(
                    source_id=source.source_id,
                    fetched_at=self._clock().timestamp(),
                    content_hash=document.content_hash,
                    chunk_count=0,
                    parser_used="ingestion",
                    status=CrawlStatus.FAILED.value,
                    error_message=str(exc),
                    operator_or_job_id=operator_or_job_id,
                )


def load_seed_documents(path: Path) -> tuple[SeedDocument, ...]:
    documents: list[SeedDocument] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            documents.append(
                SeedDocument(
                    source_id=item["source_id"],
                    url=item["url"],
                    title=item["title"],
                    publisher=item["publisher"],
                    text=item["text"],
                    topic=item.get("topic", "一般衛教"),
                    language=Language(item.get("language", Language.ZH_TW.value)),
                    audience=Audience(item.get("audience", Audience.GENERAL_PUBLIC.value)),
                    medical_scope=MedicalScope(
                        item.get("medical_scope", MedicalScope.HEALTH_EDUCATION.value)
                    ),
                    published_at=_parse_date(item.get("published_at")),
                    updated_at=_parse_date(item.get("updated_at")),
                )
            )
    return tuple(documents)


def group_seed_documents_by_source(
    documents: tuple[SeedDocument, ...],
) -> dict[str, tuple[SeedDocument, ...]]:
    grouped: dict[str, list[SeedDocument]] = {}
    for document in documents:
        grouped.setdefault(document.source_id, []).append(document)
    return {source_id: tuple(rows) for source_id, rows in grouped.items()}


def _seed_to_document(source: Source, seed: SeedDocument, retrieved_at: date) -> RagDocument:
    content_hash = _hash(seed.text)
    document_id = _document_id(source.source_id, seed.url, content_hash)
    return RagDocument(
        document_id=document_id,
        source_id=source.source_id,
        url=seed.url,
        title=seed.title,
        publisher=seed.publisher or source.publisher,
        text=seed.text,
        content_hash=content_hash,
        source_type=source.source_type,
        language=seed.language,
        topic=seed.topic,
        audience=seed.audience,
        medical_scope=seed.medical_scope,
        trust_level=source.trust_level,
        copyright_status=source.copyright_status,
        published_at=seed.published_at,
        updated_at=seed.updated_at,
        retrieved_at=retrieved_at,
    )


def _page_to_document(source: Source, page: ParsedPage, retrieved_at: date) -> RagDocument:
    content_hash = _hash(page.text)
    document_id = _document_id(source.source_id, page.url, content_hash)
    return RagDocument(
        document_id=document_id,
        source_id=source.source_id,
        url=page.url,
        title=page.title or source.title,
        publisher=source.publisher,
        text=page.text,
        content_hash=content_hash,
        source_type=source.source_type,
        language=Language.ZH_TW if _looks_zh_tw(page.text) else Language.EN,
        topic=_infer_topic(f"{page.title}\n{page.text}"),
        audience=Audience.GENERAL_PUBLIC,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=source.trust_level,
        copyright_status=source.copyright_status,
        published_at=page.published_at,
        updated_at=page.published_at,
        retrieved_at=retrieved_at,
    )


def _metadata_for(document: RagDocument, source: Source) -> ChunkMetadata:
    return ChunkMetadata(
        source_id=document.source_id,
        document_id=document.document_id,
        chunk_id=f"{document.document_id}#chunk-0",
        title=document.title,
        publisher=document.publisher,
        source_url=document.url,
        source_type=document.source_type,
        language=document.language,
        topic=document.topic,
        audience=document.audience,
        medical_scope=document.medical_scope,
        trust_level=document.trust_level,
        approved_for_rag=source.approved_for_rag,
        copyright_status=document.copyright_status,
        source_published_at=document.published_at,
        source_updated_at=document.updated_at,
        retrieved_at=document.retrieved_at,
        last_reviewed_at=document.retrieved_at,
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_id(source_id: str, url: str, content_hash: str) -> str:
    slug = _SLUG_RE.sub("-", url.rsplit("/", 1)[-1] or source_id).strip("-")[:40]
    return f"{source_id}:{slug}:{content_hash[:12]}"


def _infer_topic(text: str) -> str:
    for topic, hints in _TOPIC_HINTS.items():
        if any(hint in text for hint in hints):
            return topic
    return "一般衛教"


def _looks_zh_tw(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text[:1000])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)
