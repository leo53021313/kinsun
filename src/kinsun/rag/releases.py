"""RAG 版本化索引、品質閘門與原子發布。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kinsun.db import Executor, StoreError
from kinsun.rag.schemas import RAG_EMBEDDING_DIMENSIONS, ContentPolicy


class RagReleaseError(Exception):
    """RAG release 狀態或資料庫操作失敗。"""


class ReleaseStatus(StrEnum):
    BUILDING = "building"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


@dataclass(frozen=True)
class RagIndexRelease:
    index_version: str
    status: ReleaseStatus
    embedding_model: str
    embedding_dimensions: int
    content_policy: ContentPolicy
    quality_metrics: dict[str, Any]
    relevance_threshold: float | None
    started_at: float
    completed_at: float | None
    published_at: float | None
    error_message: str | None


@dataclass(frozen=True)
class QualityGateInput:
    attempted_documents: int
    failed_documents: int
    safety_pass_rate: float
    supported_top3_recall: float
    unsupported_false_positive_rate: float
    citation_correctness: float
    relevance_threshold: float


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    metrics: dict[str, Any]
    failures: tuple[str, ...]


class PgRagReleaseStore:
    def __init__(self, db: Executor, *, clock=time.time) -> None:
        self._db = db
        self._clock = clock

    def begin_release(
        self,
        index_version: str,
        *,
        embedding_model: str,
        content_policy: ContentPolicy,
        embedding_dimensions: int = RAG_EMBEDDING_DIMENSIONS,
    ) -> RagIndexRelease:
        if not index_version.strip():
            raise RagReleaseError("index_version 不可空白。")
        if embedding_dimensions != RAG_EMBEDDING_DIMENSIONS:
            raise RagReleaseError(f"RAG embedding 維度必須為 {RAG_EMBEDDING_DIMENSIONS}。")
        started_at = self._clock()
        self._execute(
            """
            INSERT INTO rag_index_releases (
                index_version, status, embedding_model, embedding_dimensions,
                content_policy, quality_metrics, started_at
            ) VALUES (%s,'building',%s,%s,%s,'{}'::jsonb,%s)
            """,
            (
                index_version,
                embedding_model,
                embedding_dimensions,
                content_policy.value,
                started_at,
            ),
        )
        release = self.get(index_version)
        if release is None:  # pragma: no cover - DB INSERT 後的防禦式檢查
            raise RagReleaseError("建立 RAG release 後無法讀回。")
        return release

    def get(self, index_version: str) -> RagIndexRelease | None:
        row = self._query_one(
            f"{_RELEASE_SELECT} WHERE index_version = %s",
            (index_version,),
        )
        return _row_to_release(row) if row else None

    def get_active(self) -> RagIndexRelease | None:
        row = self._query_one(f"{_RELEASE_SELECT} WHERE status = 'active'")
        return _row_to_release(row) if row else None

    def list_releases(self, *, limit: int = 20) -> tuple[RagIndexRelease, ...]:
        rows = self._query(
            f"{_RELEASE_SELECT} ORDER BY started_at DESC LIMIT %s",
            (limit,),
        )
        return tuple(_row_to_release(row) for row in rows)

    def mark_failed(
        self,
        index_version: str,
        *,
        error_message: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE rag_index_releases
            SET status='failed', quality_metrics=%s::jsonb, completed_at=%s,
                error_message=%s
            WHERE index_version=%s AND status IN ('building','candidate')
            """,
            (
                json.dumps(metrics or {}, ensure_ascii=False),
                self._clock(),
                error_message,
                index_version,
            ),
        )

    def evaluate_and_publish(
        self,
        index_version: str,
        gate_input: QualityGateInput,
    ) -> QualityGateResult:
        structural = self.structural_metrics(index_version)
        active = self.get_active()
        previous_document_count = (
            int(active.quality_metrics.get("document_count", 0)) if active else 0
        )
        result = evaluate_quality_gate(
            structural,
            gate_input,
            previous_document_count=previous_document_count,
        )
        if not result.passed:
            self.mark_failed(
                index_version,
                error_message="；".join(result.failures),
                metrics=result.metrics,
            )
            return result
        self._execute(
            """
            UPDATE rag_index_releases
            SET status='candidate', quality_metrics=%s::jsonb,
                relevance_threshold=%s, completed_at=%s, error_message=NULL
            WHERE index_version=%s AND status='building'
            """,
            (
                json.dumps(result.metrics, ensure_ascii=False),
                gate_input.relevance_threshold,
                self._clock(),
                index_version,
            ),
        )
        self.publish(index_version)
        return result

    def publish(self, index_version: str) -> None:
        try:
            with self._db.transaction() as tx:
                target = tx.query_one(
                    """
                    SELECT status FROM rag_index_releases
                    WHERE index_version=%s FOR UPDATE
                    """,
                    (index_version,),
                )
                if target is None or target[0] != ReleaseStatus.CANDIDATE.value:
                    raise RagReleaseError("只有通過品質閘門的 candidate release 可以發布。")
                tx.execute(
                    """
                    UPDATE rag_index_releases
                    SET status='superseded'
                    WHERE status='active'
                    """
                )
                tx.execute(
                    """
                    UPDATE rag_index_releases
                    SET status='active', published_at=%s
                    WHERE index_version=%s
                    """,
                    (self._clock(), index_version),
                )
        except StoreError as exc:
            raise RagReleaseError(str(exc)) from exc

    def rollback(self, index_version: str) -> None:
        try:
            with self._db.transaction() as tx:
                target = tx.query_one(
                    """
                    SELECT status FROM rag_index_releases
                    WHERE index_version=%s FOR UPDATE
                    """,
                    (index_version,),
                )
                allowed = {ReleaseStatus.ACTIVE.value, ReleaseStatus.SUPERSEDED.value}
                if target is None or target[0] not in allowed:
                    raise RagReleaseError("只能 rollback 到已成功發布過的 release。")
                tx.execute(
                    """
                    UPDATE rag_index_releases
                    SET status='superseded'
                    WHERE status='active' AND index_version<>%s
                    """,
                    (index_version,),
                )
                tx.execute(
                    """
                    UPDATE rag_index_releases
                    SET status='active', published_at=%s
                    WHERE index_version=%s
                    """,
                    (self._clock(), index_version),
                )
        except StoreError as exc:
            raise RagReleaseError(str(exc)) from exc

    def structural_metrics(self, index_version: str) -> dict[str, int]:
        row = self._query_one(
            """
            WITH release_documents AS MATERIALIZED (
                SELECT rd.document_id, d.url, d.content_hash, s.source_role
                FROM rag_release_documents rd
                JOIN rag_documents d ON d.document_id=rd.document_id
                JOIN rag_sources s ON s.source_id=d.source_id
                WHERE rd.index_version=%s
            ),
            release_chunks AS MATERIALIZED (
                SELECT c.chunk_id, c.document_id, c.embedding, c.text
                FROM rag_release_chunks rc
                JOIN rag_chunks c ON c.chunk_id=rc.chunk_id
                WHERE rc.index_version=%s
            )
            SELECT
                (SELECT COUNT(*) FROM release_documents),
                (SELECT COUNT(*) FROM release_chunks),
                (SELECT COUNT(*) FROM release_chunks WHERE embedding IS NULL),
                (SELECT COUNT(*) FROM release_chunks WHERE length(text) > 700),
                (SELECT COUNT(*) FROM release_chunks WHERE btrim(text) = ''),
                (SELECT COUNT(DISTINCT url) FROM release_documents),
                (SELECT COUNT(DISTINCT content_hash) FROM release_documents),
                (
                    SELECT COUNT(*)
                    FROM release_documents rd
                    WHERE rd.source_role='answer'
                      AND NOT EXISTS (
                          SELECT 1 FROM release_chunks rc
                          WHERE rc.document_id=rd.document_id
                      )
                ),
                (
                    SELECT COUNT(*)
                    FROM release_chunks rc
                    WHERE NOT EXISTS (
                          SELECT 1 FROM release_documents rd
                          WHERE rd.document_id=rc.document_id
                      )
                )
            """,
            (index_version, index_version),
        )
        if row is None:
            return {
                "document_count": 0,
                "chunk_count": 0,
                "empty_embedding_count": 0,
                "overlong_chunk_count": 0,
                "empty_chunk_count": 0,
                "duplicate_url_count": 0,
                "duplicate_content_hash_count": 0,
                "orphan_document_count": 0,
                "orphan_chunk_count": 0,
            }
        counts = tuple(int(value or 0) for value in row)
        (
            document_count,
            chunk_count,
            empty_embeddings,
            overlong,
            empty_chunks,
            unique_urls,
            unique_content_hashes,
            orphans,
            orphan_chunks,
        ) = counts
        return {
            "document_count": document_count,
            "chunk_count": chunk_count,
            "empty_embedding_count": empty_embeddings,
            "overlong_chunk_count": overlong,
            "empty_chunk_count": empty_chunks,
            "duplicate_url_count": max(0, document_count - unique_urls),
            "duplicate_content_hash_count": max(0, document_count - unique_content_hashes),
            "orphan_document_count": orphans,
            "orphan_chunk_count": orphan_chunks,
        }

    def cleanup(self, *, audit_retention_days: int) -> None:
        cutoff = self._clock() - audit_retention_days * 86400
        successful = self._query(
            """
            SELECT index_version FROM rag_index_releases
            WHERE status IN ('active','superseded')
            ORDER BY COALESCE(published_at, completed_at, started_at) DESC
            """
        )
        keep = tuple(row[0] for row in successful[:3])
        if keep:
            self._execute(
                """
                DELETE FROM rag_index_releases
                WHERE status='superseded' AND NOT (index_version = ANY(%s))
                """,
                (list(keep),),
            )
        self._execute(
            """
            DELETE FROM rag_index_releases
            WHERE status='failed' AND completed_at < %s
            """,
            (cutoff,),
        )
        self._execute(
            """
            DELETE FROM rag_chunks c
            WHERE EXISTS (SELECT 1 FROM rag_index_releases WHERE status='active')
              AND NOT EXISTS (
                SELECT 1 FROM rag_release_chunks rc WHERE rc.chunk_id=c.chunk_id
            )
            """
        )
        self._execute(
            """
            DELETE FROM rag_documents d
            WHERE EXISTS (SELECT 1 FROM rag_index_releases WHERE status='active')
              AND NOT EXISTS (
                SELECT 1 FROM rag_release_documents rd WHERE rd.document_id=d.document_id
            )
            """
        )
        self._execute(
            "DELETE FROM rag_ingestion_audit_logs WHERE fetched_at < %s",
            (cutoff,),
        )

    def _execute(self, sql: str, params: tuple = ()) -> None:
        try:
            self._db.execute(sql, params)
        except StoreError as exc:
            raise RagReleaseError(str(exc)) from exc

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            return self._db.query(sql, params)
        except StoreError as exc:
            raise RagReleaseError(str(exc)) from exc

    def _query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            return self._db.query_one(sql, params)
        except StoreError as exc:
            raise RagReleaseError(str(exc)) from exc


def evaluate_quality_gate(
    structural: dict[str, int],
    gate_input: QualityGateInput,
    *,
    previous_document_count: int = 0,
) -> QualityGateResult:
    attempted = max(gate_input.attempted_documents, 0)
    success_rate = 0.0 if attempted == 0 else 1 - gate_input.failed_documents / attempted
    metrics: dict[str, Any] = {
        **structural,
        "attempted_documents": attempted,
        "failed_documents": gate_input.failed_documents,
        "success_rate": success_rate,
        "safety_pass_rate": gate_input.safety_pass_rate,
        "supported_top3_recall": gate_input.supported_top3_recall,
        "unsupported_false_positive_rate": gate_input.unsupported_false_positive_rate,
        "citation_correctness": gate_input.citation_correctness,
    }
    failures: list[str] = []
    if success_rate < 0.9:
        failures.append("入庫成功率低於 90%")
    if previous_document_count and structural["document_count"] < previous_document_count * 0.8:
        failures.append("文件數較前版下降超過 20%")
    for key, label in (
        ("duplicate_url_count", "有重複 URL"),
        ("duplicate_content_hash_count", "有重複內容 hash"),
        ("orphan_document_count", "有孤兒文件"),
        ("orphan_chunk_count", "有孤兒 chunk"),
        ("empty_embedding_count", "有空 embedding"),
        ("overlong_chunk_count", "有超長 chunk"),
        ("empty_chunk_count", "有空 chunk"),
    ):
        if structural[key] > 0:
            failures.append(label)
    if gate_input.safety_pass_rate < 1:
        failures.append("安全案例未達 100%")
    if gate_input.supported_top3_recall < 0.8:
        failures.append("supported query top-3 recall 低於 80%")
    if gate_input.unsupported_false_positive_rate > 0.05:
        failures.append("unsupported false-positive 高於 5%")
    return QualityGateResult(not failures, metrics, tuple(failures))


_RELEASE_SELECT = """
SELECT index_version, status, embedding_model, embedding_dimensions, content_policy,
       quality_metrics, relevance_threshold, started_at, completed_at, published_at,
       error_message
FROM rag_index_releases
"""


def _row_to_release(row: tuple) -> RagIndexRelease:
    metrics = row[5]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    return RagIndexRelease(
        index_version=str(row[0]),
        status=ReleaseStatus(row[1]),
        embedding_model=str(row[2]),
        embedding_dimensions=int(row[3]),
        content_policy=ContentPolicy(row[4]),
        quality_metrics=dict(metrics or {}),
        relevance_threshold=float(row[6]) if row[6] is not None else None,
        started_at=float(row[7]),
        completed_at=float(row[8]) if row[8] is not None else None,
        published_at=float(row[9]) if row[9] is not None else None,
        error_message=str(row[10]) if row[10] is not None else None,
    )
