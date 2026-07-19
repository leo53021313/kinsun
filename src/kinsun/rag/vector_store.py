"""向量儲存介面、in-memory 測試實作與 pgvector 實作。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
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
    SourceRole,
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


class PgVectorStore:
    def __init__(
        self,
        db: Executor,
        *,
        index_version: str | None = None,
        embedding_model: str = "",
    ) -> None:
        self._db = db
        self._index_version = index_version
        self._embedding_model = embedding_model

    def upsert_source(self, source: Source) -> None:
        self._execute(
            """
            INSERT INTO rag_sources (
                source_id, title, url, publisher, source_type, trust_level,
                copyright_status, recommended_status, approved_for_rag, allowed_domains, notes,
                source_role
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                notes=EXCLUDED.notes,
                source_role=EXCLUDED.source_role
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
                source.role.value,
            ),
        )

    def upsert_document(self, document: RagDocument) -> None:
        self._execute(
            """
            INSERT INTO rag_documents AS current_document (
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
            WHERE NOT EXISTS (
                SELECT 1
                FROM rag_release_documents rd
                JOIN rag_index_releases r ON r.index_version=rd.index_version
                WHERE rd.document_id=current_document.document_id AND r.status='active'
            )
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

    def save_document(
        self,
        document: RagDocument,
        prepared_chunks: tuple[tuple[DocumentChunk, tuple[float, ...]], ...],
        *,
        index_version: str | None,
        embedding_model_name: str,
        embedding_dimensions: int,
        fetched_at: float,
        parser_used: str,
        operator_or_job_id: str,
    ) -> None:
        """以單一 transaction 寫入文件、chunks、版本 membership 與成功稽核。"""
        try:
            with self._db.transaction() as tx:
                embedding_model = ""
                if index_version:
                    release_row = tx.query_one(
                        """
                        SELECT embedding_model, embedding_dimensions
                        FROM rag_index_releases WHERE index_version=%s
                        """,
                        (index_version,),
                    )
                    if release_row is None:
                        raise RagStoreError(f"找不到 RAG release：{index_version}")
                    embedding_model = str(release_row[0])
                    release_configuration = (embedding_model, int(release_row[1]))
                    runtime_configuration = (embedding_model_name, embedding_dimensions)
                    if release_configuration != runtime_configuration:
                        raise RagStoreError(
                            "RAG release 與文件 embedding 設定不一致："
                            f"release={release_configuration} runtime={runtime_configuration}"
                        )
                elif embedding_model_name:
                    embedding_model = embedding_model_name
                store = PgVectorStore(tx, embedding_model=embedding_model)
                existing_document = tx.query_one(
                    """
                    SELECT document_id FROM rag_documents
                    WHERE source_id=%s AND content_hash=%s LIMIT 1
                    """,
                    (document.source_id, document.content_hash),
                )
                stored_document = (
                    replace(document, document_id=str(existing_document[0]))
                    if existing_document and existing_document[0] != document.document_id
                    else document
                )
                store.upsert_document(stored_document)
                for chunk, vector in prepared_chunks:
                    remapped_chunk = _remap_chunk_document(chunk, stored_document.document_id)
                    stored_chunk = _release_chunk_variant(remapped_chunk, embedding_model)
                    store.add(stored_chunk, vector)
                    if index_version:
                        tx.execute(
                            """
                            INSERT INTO rag_release_chunks (index_version, chunk_id)
                            VALUES (%s,%s) ON CONFLICT DO NOTHING
                            """,
                            (index_version, stored_chunk.metadata.chunk_id),
                        )
                if index_version:
                    tx.execute(
                        """
                        INSERT INTO rag_release_documents (index_version, document_id)
                        VALUES (%s,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (index_version, stored_document.document_id),
                    )
                store.log_ingestion(
                    source_id=stored_document.source_id,
                    document_id=stored_document.document_id,
                    url=stored_document.url,
                    fetched_at=fetched_at,
                    content_hash=stored_document.content_hash,
                    chunk_count=len(prepared_chunks),
                    parser_used=parser_used,
                    status="success",
                    error_message=None,
                    operator_or_job_id=operator_or_job_id,
                )
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc

    def save_discovery_document(
        self,
        document: RagDocument,
        *,
        index_version: str,
        fetched_at: float,
        operator_or_job_id: str,
    ) -> None:
        """保存 discovery 文件與稽核，不建立不可作答的 embeddings。"""
        try:
            with self._db.transaction() as tx:
                release = tx.query_one(
                    "SELECT 1 FROM rag_index_releases WHERE index_version=%s",
                    (index_version,),
                )
                if release is None:
                    raise RagStoreError(f"找不到 RAG release：{index_version}")
                existing_document = tx.query_one(
                    "SELECT document_id FROM rag_documents WHERE source_id=%s "
                    "AND content_hash=%s LIMIT 1",
                    (document.source_id, document.content_hash),
                )
                stored_document = (
                    replace(document, document_id=str(existing_document[0]))
                    if existing_document and existing_document[0] != document.document_id
                    else document
                )
                store = PgVectorStore(tx)
                store.upsert_document(stored_document)
                tx.execute(
                    """
                    INSERT INTO rag_release_documents (index_version, document_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING
                    """,
                    (index_version, stored_document.document_id),
                )
                store.log_ingestion(
                    source_id=stored_document.source_id,
                    document_id=stored_document.document_id,
                    url=stored_document.url,
                    fetched_at=fetched_at,
                    content_hash=stored_document.content_hash,
                    chunk_count=0,
                    parser_used="discovery",
                    status="success",
                    error_message=None,
                    operator_or_job_id=operator_or_job_id,
                )
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc

    def reuse_document(
        self,
        document: RagDocument,
        *,
        source_role: SourceRole,
        index_version: str,
        fetched_at: float,
        operator_or_job_id: str,
    ) -> bool:
        """模型、維度、角色與品質皆相容時，重用已發布文件的 chunks／embeddings。"""
        row = self._query_one(
            """
            SELECT d.document_id, old_r.index_version, COUNT(old_rc.chunk_id)
            FROM rag_documents d
            JOIN rag_release_documents old_rd ON old_rd.document_id=d.document_id
            JOIN rag_index_releases old_r ON old_r.index_version=old_rd.index_version
            JOIN rag_index_releases new_r ON new_r.index_version=%s
            JOIN rag_release_chunks old_rc ON old_rc.index_version=old_r.index_version
            JOIN rag_chunks c
              ON c.chunk_id=old_rc.chunk_id AND c.document_id=d.document_id
            WHERE d.source_id=%s AND d.content_hash=%s
              AND old_r.status IN ('active','superseded','failed')
              AND old_r.embedding_model=new_r.embedding_model
              AND old_r.embedding_dimensions=new_r.embedding_dimensions
              AND c.embedding_model=new_r.embedding_model
              AND c.source_role=%s
              AND NOT EXISTS (
                  SELECT 1
                  FROM rag_release_chunks bad_rc
                  JOIN rag_chunks bad_c ON bad_c.chunk_id=bad_rc.chunk_id
                  WHERE bad_rc.index_version=old_r.index_version
                    AND bad_c.document_id=d.document_id
                    AND (
                        bad_c.embedding IS NULL
                        OR length(bad_c.text) NOT BETWEEN 1 AND 700
                        OR bad_c.source_role<>%s
                        OR bad_c.embedding_model<>new_r.embedding_model
                    )
              )
            GROUP BY d.document_id, old_r.index_version, old_r.status, old_r.published_at
            HAVING COUNT(old_rc.chunk_id) > 0
            ORDER BY CASE old_r.status
                         WHEN 'active' THEN 0
                         WHEN 'superseded' THEN 1
                         ELSE 2
                     END,
                     old_r.published_at DESC NULLS LAST
            LIMIT 1
            """,
            (
                index_version,
                document.source_id,
                document.content_hash,
                source_role.value,
                source_role.value,
            ),
        )
        if row is None:
            return False
        document_id = str(row[0])
        old_index_version = str(row[1])
        chunk_count = int(row[2])
        try:
            with self._db.transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO rag_release_documents (index_version, document_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING
                    """,
                    (index_version, document_id),
                )
                tx.execute(
                    """
                    INSERT INTO rag_release_chunks (index_version, chunk_id)
                    SELECT %s, rc.chunk_id
                    FROM rag_release_chunks rc
                    JOIN rag_chunks c ON c.chunk_id=rc.chunk_id
                    WHERE rc.index_version=%s AND c.document_id=%s
                    ON CONFLICT DO NOTHING
                    """,
                    (index_version, old_index_version, document_id),
                )
                PgVectorStore(tx).log_ingestion(
                    source_id=document.source_id,
                    document_id=document_id,
                    url=document.url,
                    fetched_at=fetched_at,
                    content_hash=document.content_hash,
                    chunk_count=chunk_count,
                    parser_used="reuse",
                    status="success",
                    error_message=None,
                    operator_or_job_id=operator_or_job_id,
                )
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc
        return True

    def list_active_document_urls(self) -> tuple[tuple[str, str], ...]:
        rows = self._query(
            """
            SELECT d.source_id, d.url
            FROM rag_release_documents rd
            JOIN rag_index_releases r ON r.index_version=rd.index_version
            JOIN rag_documents d ON d.document_id=rd.document_id
            WHERE r.status='active'
            ORDER BY d.source_id, d.url
            """
        )
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def add(self, chunk: DocumentChunk, vector: tuple[float, ...]) -> None:
        metadata = chunk.metadata
        self._execute(
            """
            INSERT INTO rag_chunks AS current_chunk (
                chunk_id, document_id, source_id, text, embedding, title, publisher,
                source_url, source_type, language, topic, audience, medical_scope,
                trust_level, approved_for_rag, copyright_status, source_published_at,
                source_updated_at, retrieved_at, last_reviewed_at, version, source_role,
                embedding_model
            ) VALUES (
                %s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
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
                version=EXCLUDED.version,
                source_role=EXCLUDED.source_role,
                embedding_model=EXCLUDED.embedding_model
            WHERE NOT EXISTS (
                SELECT 1
                FROM rag_release_chunks rc
                JOIN rag_index_releases r ON r.index_version=rc.index_version
                WHERE rc.chunk_id=current_chunk.chunk_id AND r.status='active'
            )
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
                metadata.source_role.value,
                self._embedding_model,
            ),
        )

    def log_ingestion(
        self,
        *,
        source_id: str,
        fetched_at: float,
        document_id: str = "",
        url: str = "",
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
                status, error_message, operator_or_job_id, document_id, url
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                document_id,
                url,
            ),
        )

    def log_skipped_documents(
        self,
        documents: tuple[tuple[RagDocument, str], ...],
        *,
        fetched_at: float,
        parser_used: str,
        operator_or_job_id: str,
        batch_size: int = 200,
    ) -> None:
        """批次寫入大量捨棄稽核，避免跨網路逐筆往返。"""
        if batch_size <= 0:
            raise ValueError("batch_size 必須大於 0")
        columns_per_row = 10
        row_placeholder = "(" + ",".join(["%s"] * columns_per_row) + ")"
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            params: list[object] = []
            for document, reason in batch:
                params.extend(
                    (
                        document.source_id,
                        fetched_at,
                        document.content_hash,
                        0,
                        parser_used,
                        "skipped",
                        reason,
                        operator_or_job_id,
                        document.document_id,
                        document.url,
                    )
                )
            self._execute(
                """
                INSERT INTO rag_ingestion_audit_logs (
                    source_id, fetched_at, content_hash, chunk_count, parser_used,
                    status, error_message, operator_or_job_id, document_id, url
                ) VALUES
                """
                + ",".join([row_placeholder] * len(batch)),
                tuple(params),
            )

    def reset(self) -> None:
        self._execute("DELETE FROM rag_ingestion_audit_logs")
        self._execute("DELETE FROM rag_index_releases")
        self._execute("DELETE FROM rag_chunks")
        self._execute("DELETE FROM rag_documents")
        self._execute("DELETE FROM rag_sources")

    def search(
        self,
        query_vector: tuple[float, ...],
        *,
        top_k: int = 5,
    ) -> tuple[SearchResult, ...]:
        release_filter = "r.status = 'active'"
        release_params: tuple[object, ...] = ()
        if self._index_version:
            release_filter = "rd.index_version = %s"
            release_params = (self._index_version,)
        rows = self._query(
            f"""
            SELECT
                c.chunk_id, c.document_id, c.source_id, c.text, c.title, c.publisher,
                c.source_url, c.source_type, c.language, c.topic, c.audience,
                c.medical_scope, c.trust_level, c.approved_for_rag, c.copyright_status,
                c.source_published_at, c.source_updated_at, c.retrieved_at,
                c.last_reviewed_at, c.version, c.source_role,
                1 - (c.embedding <=> %s::vector) AS score
            FROM rag_chunks c
            JOIN rag_release_chunks rc ON rc.chunk_id = c.chunk_id
            JOIN rag_index_releases r ON r.index_version = rc.index_version
            JOIN rag_release_documents rd
              ON rd.index_version = rc.index_version AND rd.document_id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND {release_filter}
              AND c.approved_for_rag
              AND c.source_role='answer'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                _vector_literal(query_vector),
                *release_params,
                _vector_literal(query_vector),
                top_k,
            ),
        )
        return tuple(_row_to_result(row, retrieval_method="vector") for row in rows)

    def keyword_search(self, query: str, *, top_k: int = 5) -> tuple[SearchResult, ...]:
        terms = extract_keyword_terms(query)
        if not terms:
            return ()
        clauses = []
        where_params: list[object] = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.append("(c.title ILIKE %s OR c.topic ILIKE %s OR c.text ILIKE %s)")
            where_params.extend([pattern, pattern, pattern])
        score_parts = []
        score_params: list[object] = []
        for term in terms:
            pattern = f"%{term}%"
            score_parts.append("CASE WHEN c.title ILIKE %s THEN 2 ELSE 0 END")
            score_parts.append("CASE WHEN c.topic ILIKE %s THEN 2 ELSE 0 END")
            score_parts.append("CASE WHEN c.text ILIKE %s THEN 1 ELSE 0 END")
            score_params.extend([pattern, pattern, pattern])
        release_filter = "r.status = 'active'"
        release_params: list[object] = []
        if self._index_version:
            release_filter = "rd.index_version = %s"
            release_params.append(self._index_version)
        score_denominator = max(1, len(terms) * 5)
        params = [*score_params, score_denominator, *release_params, *where_params, top_k]
        rows = self._query(
            f"""
            SELECT
                c.chunk_id, c.document_id, c.source_id, c.text, c.title, c.publisher,
                c.source_url, c.source_type, c.language, c.topic, c.audience,
                c.medical_scope, c.trust_level, c.approved_for_rag, c.copyright_status,
                c.source_published_at, c.source_updated_at, c.retrieved_at,
                c.last_reviewed_at, c.version, c.source_role,
                ({" + ".join(score_parts)})::DOUBLE PRECISION / %s AS score
            FROM rag_chunks c
            JOIN rag_release_chunks rc ON rc.chunk_id = c.chunk_id
            JOIN rag_index_releases r ON r.index_version = rc.index_version
            JOIN rag_release_documents rd
              ON rd.index_version = rc.index_version AND rd.document_id = c.document_id
            WHERE {release_filter}
              AND c.approved_for_rag
              AND c.source_role='answer'
              AND ({" OR ".join(clauses)})
            ORDER BY score DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return tuple(_row_to_result(row, terms=terms, retrieval_method="keyword") for row in rows)

    def active_embedding_configuration(self) -> tuple[str, int] | None:
        where = "status = 'active'"
        params: tuple[object, ...] = ()
        if self._index_version:
            where = "index_version = %s"
            params = (self._index_version,)
        row = self._query_one(
            f"""
            SELECT embedding_model, embedding_dimensions
            FROM rag_index_releases
            WHERE {where}
            """,
            params,
        )
        if row is None:
            return None
        return str(row[0]), int(row[1])

    def active_release_version(self) -> str:
        if self._index_version:
            return self._index_version
        row = self._query_one("SELECT index_version FROM rag_index_releases WHERE status='active'")
        return str(row[0]) if row else ""

    def active_relevance_threshold(self) -> float | None:
        where = "status='active'"
        params: tuple[object, ...] = ()
        if self._index_version:
            where = "index_version=%s"
            params = (self._index_version,)
        row = self._query_one(
            f"SELECT relevance_threshold FROM rag_index_releases WHERE {where}",
            params,
        )
        if row is None or row[0] is None:
            return None
        return float(row[0])

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

    def _query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            return self._db.query_one(sql, params)
        except StoreError as exc:
            raise RagStoreError(str(exc)) from exc


def _release_chunk_variant(chunk: DocumentChunk, embedding_model: str) -> DocumentChunk:
    """讓不同 embedding／來源角色的 chunk 可同時存在，並由 release 精確選用。"""
    if not embedding_model:
        return chunk
    variant = hashlib.sha256(
        f"{embedding_model}\0{chunk.metadata.source_role.value}".encode()
    ).hexdigest()[:12]
    metadata = replace(
        chunk.metadata,
        chunk_id=f"{chunk.metadata.chunk_id}@{variant}",
    )
    return replace(chunk, metadata=metadata)


def _remap_chunk_document(chunk: DocumentChunk, document_id: str) -> DocumentChunk:
    if chunk.metadata.document_id == document_id:
        return chunk
    original_id = chunk.metadata.document_id
    suffix = chunk.metadata.chunk_id.removeprefix(original_id)
    metadata = replace(
        chunk.metadata,
        document_id=document_id,
        chunk_id=f"{document_id}{suffix}",
    )
    return replace(chunk, metadata=metadata)


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
        source_role,
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
        source_role=SourceRole(source_role),
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
