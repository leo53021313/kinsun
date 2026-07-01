"""向量儲存介面、in-memory 測試實作與 pgvector 實作。"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from kinsun.db import Executor, StoreError
from kinsun.rag.retriever import extract_keyword_terms
from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    RagDocument,
    SearchResult,
    Source,
    SourceType,
    TrustLevel,
)


class RagStoreError(Exception):
    """衛教 RAG 儲存層失敗。"""


class HybridVectorStore(Protocol):
    def add(self, chunk: DocumentChunk, vector: tuple[float, ...]) -> None: ...
    def search(
        self,
        query_vector: tuple[float, ...],
        *,
        top_k: int = 5,
    ) -> tuple[SearchResult, ...]: ...
    def keyword_search(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._entries: list[tuple[DocumentChunk, tuple[float, ...]]] = []

    def add(self, chunk: DocumentChunk, vector: tuple[float, ...]) -> None:
        self._entries.append((chunk, vector))

    def search(
        self,
        query_vector: tuple[float, ...],
        *,
        top_k: int = 5,
    ) -> tuple[SearchResult, ...]:
        scored = [
            SearchResult(
                chunk=chunk,
                score=_cosine(query_vector, vector),
                retrieval_method="vector",
            )
            for chunk, vector in self._entries
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return tuple(scored[:top_k])

    def keyword_search(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        terms = extract_keyword_terms(query)
        results: list[SearchResult] = []
        for chunk, _ in self._entries:
            searchable_text = f"{chunk.metadata.title} {chunk.metadata.topic} {chunk.text}".lower()
            matched = tuple(term for term in terms if term.lower() in searchable_text)
            if not matched:
                continue
            score = len(matched) / max(len(terms), 1)
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=matched,
                    retrieval_method="keyword",
                )
            )
        results.sort(key=lambda result: result.score, reverse=True)
        return tuple(results[:top_k])


class PgVectorStore:
    def __init__(self, db: Executor) -> None:
        self._db = db

    def upsert_source(self, source: Source) -> None:
        self._execute(
            """
            INSERT INTO rag_sources (
                source_id, title, url, publisher, source_type, trust_level,
                copyright_status, recommended_status, approved_for_rag, allowed_domains, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source_id) DO UPDATE SET
                title=EXCLUDED.title,
                url=EXCLUDED.url,
                publisher=EXCLUDED.publisher,
                source_type=EXCLUDED.source_type,
                trust_level=EXCLUDED.trust_level,
                copyright_status=EXCLUDED.copyright_status,
                recommended_status=EXCLUDED.recommended_status,
                approved_for_rag=EXCLUDED.approved_for_rag,
                allowed_domains=EXCLUDED.allowed_domains,
                notes=EXCLUDED.notes
            """,
            (
                source.source_id,
                source.title,
                source.url,
                source.publisher,
                source.source_type.value,
                source.trust_level.value,
                source.copyright_status.value,
                source.recommended_status.value,
                source.approved_for_rag,
                ",".join(source.allowed_domains),
                source.notes,
            ),
        )

    def upsert_document(self, document: RagDocument) -> None:
        self._execute(
            """
            INSERT INTO rag_documents (
                document_id, source_id, url, title, publisher, text, content_hash,
                source_type, language, topic, audience, medical_scope, trust_level,
                copyright_status, published_at, updated_at, retrieved_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (document_id) DO UPDATE SET
                url=EXCLUDED.url,
                title=EXCLUDED.title,
                publisher=EXCLUDED.publisher,
                text=EXCLUDED.text,
                content_hash=EXCLUDED.content_hash,
                source_type=EXCLUDED.source_type,
                language=EXCLUDED.language,
                topic=EXCLUDED.topic,
                audience=EXCLUDED.audience,
                medical_scope=EXCLUDED.medical_scope,
                trust_level=EXCLUDED.trust_level,
                copyright_status=EXCLUDED.copyright_status,
                published_at=EXCLUDED.published_at,
                updated_at=EXCLUDED.updated_at,
                retrieved_at=EXCLUDED.retrieved_at
            """,
            (
                document.document_id,
                document.source_id,
                document.url,
                document.title,
                document.publisher,
                document.text,
                document.content_hash,
                document.source_type.value,
                document.language.value,
                document.topic,
                document.audience.value,
                document.medical_scope.value,
                document.trust_level.value,
                document.copyright_status.value,
                document.published_at,
                document.updated_at,
                document.retrieved_at,
            ),
        )

    def add(self, chunk: DocumentChunk, vector: tuple[float, ...]) -> None:
        metadata = chunk.metadata
        self._execute(
            """
            INSERT INTO rag_chunks (
                chunk_id, document_id, source_id, text, embedding, title, publisher,
                source_url, source_type, language, topic, audience, medical_scope,
                trust_level, approved_for_rag, copyright_status, source_published_at,
                source_updated_at, retrieved_at, last_reviewed_at, version
            ) VALUES (
                %s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                text=EXCLUDED.text,
                embedding=EXCLUDED.embedding,
                title=EXCLUDED.title,
                publisher=EXCLUDED.publisher,
                source_url=EXCLUDED.source_url,
                source_type=EXCLUDED.source_type,
                language=EXCLUDED.language,
                topic=EXCLUDED.topic,
                audience=EXCLUDED.audience,
                medical_scope=EXCLUDED.medical_scope,
                trust_level=EXCLUDED.trust_level,
                approved_for_rag=EXCLUDED.approved_for_rag,
                copyright_status=EXCLUDED.copyright_status,
                source_published_at=EXCLUDED.source_published_at,
                source_updated_at=EXCLUDED.source_updated_at,
                retrieved_at=EXCLUDED.retrieved_at,
                last_reviewed_at=EXCLUDED.last_reviewed_at,
                version=EXCLUDED.version
            """,
            (
                metadata.chunk_id,
                metadata.document_id,
                metadata.source_id,
                chunk.text,
                _vector_literal(vector),
                metadata.title,
                metadata.publisher,
                metadata.source_url,
                metadata.source_type.value,
                metadata.language.value,
                metadata.topic,
                metadata.audience.value,
                metadata.medical_scope.value,
                metadata.trust_level.value,
                metadata.approved_for_rag,
                metadata.copyright_status.value,
                metadata.source_published_at,
                metadata.source_updated_at,
                metadata.retrieved_at,
                metadata.last_reviewed_at,
                metadata.version,
            ),
        )

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
    ) -> None:
        self._execute(
            """
            INSERT INTO rag_ingestion_audit_logs (
                source_id, fetched_at, content_hash, chunk_count, parser_used,
                status, error_message, operator_or_job_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                source_id,
                fetched_at,
                content_hash,
                chunk_count,
                parser_used,
                status,
                error_message,
                operator_or_job_id,
            ),
        )

    def reset(self) -> None:
        self._execute("DELETE FROM rag_ingestion_audit_logs")
        self._execute("DELETE FROM rag_crawl_jobs")
        self._execute("DELETE FROM rag_chunks")
        self._execute("DELETE FROM rag_documents")
        self._execute("DELETE FROM rag_sources")

    def search(
        self,
        query_vector: tuple[float, ...],
        *,
        top_k: int = 5,
    ) -> tuple[SearchResult, ...]:
        rows = self._query(
            """
            SELECT
                chunk_id, document_id, source_id, text, title, publisher, source_url,
                source_type, language, topic, audience, medical_scope, trust_level,
                approved_for_rag, copyright_status, source_published_at, source_updated_at,
                retrieved_at, last_reviewed_at, version,
                1 - (embedding <=> %s::vector) AS score
            FROM rag_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (_vector_literal(query_vector), _vector_literal(query_vector), top_k),
        )
        return tuple(_row_to_result(row, retrieval_method="vector") for row in rows)

    def keyword_search(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        terms = extract_keyword_terms(query)
        if not terms:
            return ()
        clauses = []
        params: list[object] = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.append("(title ILIKE %s OR topic ILIKE %s OR text ILIKE %s)")
            params.extend([pattern, pattern, pattern])
        score_parts = []
        for term in terms:
            pattern = f"%{term}%"
            score_parts.append("CASE WHEN title ILIKE %s THEN 2 ELSE 0 END")
            score_parts.append("CASE WHEN topic ILIKE %s THEN 2 ELSE 0 END")
            score_parts.append("CASE WHEN text ILIKE %s THEN 1 ELSE 0 END")
            params.extend([pattern, pattern, pattern])
        params.append(top_k)
        rows = self._query(
            f"""
            SELECT
                chunk_id, document_id, source_id, text, title, publisher, source_url,
                source_type, language, topic, audience, medical_scope, trust_level,
                approved_for_rag, copyright_status, source_published_at, source_updated_at,
                retrieved_at, last_reviewed_at, version,
                ({" + ".join(score_parts)})::DOUBLE PRECISION AS score
            FROM rag_chunks
            WHERE {" OR ".join(clauses)}
            ORDER BY score DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return tuple(_row_to_result(row, terms=terms, retrieval_method="keyword") for row in rows)

    def _execute(self, sql: str, params: tuple = ()) -> None:
        try:
            self._db.execute(sql, params)
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            return self._db.query(sql, params)
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("向量維度不一致")
    return sum(l_value * r_value for l_value, r_value in zip(left, right, strict=True))


def _vector_literal(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _row_to_result(
    row: tuple,
    *,
    terms: tuple[str, ...] = (),
    retrieval_method: str,
) -> SearchResult:
    (
        chunk_id,
        document_id,
        source_id,
        text,
        title,
        publisher,
        source_url,
        source_type,
        language,
        topic,
        audience,
        medical_scope,
        trust_level,
        approved_for_rag,
        copyright_status,
        source_published_at,
        source_updated_at,
        retrieved_at,
        last_reviewed_at,
        version,
        score,
    ) = row
    metadata = ChunkMetadata(
        source_id=source_id,
        document_id=document_id,
        chunk_id=chunk_id,
        title=title,
        publisher=publisher,
        source_url=source_url,
        source_type=SourceType(source_type),
        language=Language(language),
        topic=topic,
        audience=Audience(audience),
        medical_scope=MedicalScope(medical_scope),
        trust_level=TrustLevel(trust_level),
        approved_for_rag=bool(approved_for_rag),
        copyright_status=CopyrightStatus(copyright_status),
        source_published_at=_as_date(source_published_at),
        source_updated_at=_as_date(source_updated_at),
        retrieved_at=_as_date(retrieved_at) or date.today(),
        last_reviewed_at=_as_date(last_reviewed_at),
        version=version,
    )
    return SearchResult(
        chunk=DocumentChunk(text=text, metadata=metadata),
        score=float(score or 0),
        matched_terms=terms,
        retrieval_method=retrieval_method,
    )


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
