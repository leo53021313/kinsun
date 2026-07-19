"""以 active release 的已知 URL 建置下一個 RAG 候選版。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from kinsun.db import Database
from kinsun.rag.crawler import CrawlerConfig, HealthEducationCrawler
from kinsun.rag.embeddings import GeminiEmbeddingModel
from kinsun.rag.evaluation import evaluate_golden_set, load_golden_set
from kinsun.rag.ingestion import IngestionPipeline
from kinsun.rag.releases import PgRagReleaseStore, QualityGateInput
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.schemas import ContentPolicy, CrawlStatus, SourceRole
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator
from kinsun.rag.vector_store import PgVectorStore


def refresh_known_urls(
    db: Database,
    *,
    api_key: str,
    embedding_model_name: str,
    content_policy: ContentPolicy,
    audit_retention_days: int,
    crawler_delay_seconds: float = 2.0,
    embedding_delay_seconds: float = 6.0,
    embedding_retries: int = 5,
    embedding_retry_initial_delay_seconds: float = 30.0,
    embedding_retry_max_delay_seconds: float = 300.0,
    embedding_timeout_seconds: float = 60.0,
    embedding_batch_size: int = 20,
    golden_set: Path = Path("data/rag/golden_set.jsonl"),
    crawler: HealthEducationCrawler | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(UTC)
    index_version = now.strftime("rag-%Y%m%dT%H%M%SZ")
    release_store = PgRagReleaseStore(db, clock=now.timestamp)
    active = release_store.get_active()
    if active is None:
        raise RuntimeError("目前沒有 active RAG release；請先執行 migrate 建立初版。")
    release_store.begin_release(
        index_version,
        embedding_model=embedding_model_name,
        content_policy=content_policy,
    )
    store = PgVectorStore(db)
    known_urls: dict[str, list[str]] = defaultdict(list)
    for source_id, url in store.list_active_document_urls():
        known_urls[source_id].append(url)
    attempted = sum(len(urls) for urls in known_urls.values())
    embedder = GeminiEmbeddingModel(
        api_key=api_key,
        model=embedding_model_name,
        request_delay_seconds=embedding_delay_seconds,
        max_retries=embedding_retries,
        retry_initial_delay_seconds=embedding_retry_initial_delay_seconds,
        retry_max_delay_seconds=embedding_retry_max_delay_seconds,
        request_timeout_seconds=embedding_timeout_seconds,
        batch_size=embedding_batch_size,
    )
    pipeline = IngestionPipeline(store=store, embedding_model=embedder, max_chunk_chars=700)
    registry = SourceRegistry()
    validator = SourceValidator(content_policy=content_policy)
    crawler = crawler or HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=1, delay_seconds=crawler_delay_seconds)
    )
    try:
        for source_id, urls in known_urls.items():
            source = registry.get(source_id)
            validation = validator.validate(source)
            if not validation.can_ingest:
                _log_failed_urls(
                    store,
                    source_id,
                    tuple((url, "；".join(validation.issues)) for url in urls),
                    operator_or_job_id=index_version,
                    fetched_at=now.timestamp(),
                )
                continue
            result = crawler.crawl_urls(source, tuple(urls))
            pipeline.ingest_pages(
                source,
                result.pages,
                operator_or_job_id=index_version,
                index_version=index_version,
            )
            _log_failed_urls(
                store,
                source_id,
                result.failed_urls,
                operator_or_job_id=index_version,
                fetched_at=now.timestamp(),
            )
            for url in result.skipped_urls:
                _log_audit(
                    store,
                    source_id=source_id,
                    url=url,
                    status=CrawlStatus.SKIPPED.value,
                    message="已知 URL 無可抽取文字；未執行 OCR。",
                    operator_or_job_id=index_version,
                    fetched_at=now.timestamp(),
                )
            if source.role == SourceRole.DISCOVERY:
                known = set(urls)
                for page in result.pages:
                    for discovered_url in page.links:
                        if discovered_url not in known:
                            _log_audit(
                                store,
                                source_id=source_id,
                                url=discovered_url,
                                status=CrawlStatus.SKIPPED.value,
                                message="discovery 新內容候選；未自動升格為回答語料。",
                                operator_or_job_id=index_version,
                                fetched_at=now.timestamp(),
                            )

        failed = db.query_one(
            """
            SELECT COUNT(*) FROM rag_ingestion_audit_logs
            WHERE operator_or_job_id=%s AND status='failed'
            """,
            (index_version,),
        )
        evaluator = HealthEducationRetriever(
            vector_store=PgVectorStore(db, index_version=index_version),
            embedding_model=embedder,
        )
        report = evaluate_golden_set(evaluator, load_golden_set(golden_set))
        gate = release_store.evaluate_and_publish(
            index_version,
            QualityGateInput(
                attempted_documents=attempted,
                failed_documents=int(failed[0] if failed else 0),
                safety_pass_rate=report.safety_pass_rate,
                supported_top3_recall=report.supported_top3_recall,
                unsupported_false_positive_rate=report.unsupported_false_positive_rate,
                citation_correctness=report.citation_correctness,
                relevance_threshold=report.threshold,
            ),
        )
        if not gate.passed:
            raise RuntimeError(f"RAG 週更品質閘門失敗：{'；'.join(gate.failures)}")
        release_store.cleanup(audit_retention_days=audit_retention_days)
        return index_version
    except Exception as exc:
        release = release_store.get(index_version)
        if release is not None and release.status.value in {"building", "candidate"}:
            release_store.mark_failed(index_version, error_message=str(exc))
        raise


def _log_failed_urls(
    store: PgVectorStore,
    source_id: str,
    failures: tuple[tuple[str, str], ...],
    *,
    operator_or_job_id: str,
    fetched_at: float,
) -> None:
    for url, message in failures:
        _log_audit(
            store,
            source_id=source_id,
            url=url,
            status=CrawlStatus.FAILED.value,
            message=message,
            operator_or_job_id=operator_or_job_id,
            fetched_at=fetched_at,
        )


def _log_audit(
    store: PgVectorStore,
    *,
    source_id: str,
    url: str,
    status: str,
    message: str,
    operator_or_job_id: str,
    fetched_at: float,
) -> None:
    store.log_ingestion(
        source_id=source_id,
        url=url,
        fetched_at=fetched_at,
        content_hash=hashlib.sha256(url.encode("utf-8")).hexdigest(),
        chunk_count=0,
        parser_used="refresh",
        status=status,
        error_message=message,
        operator_or_job_id=operator_or_job_id,
    )
