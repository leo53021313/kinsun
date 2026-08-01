"""衛教 RAG ingestion CLI。

範例：
uv run python -m kinsun.rag.ingest --source hpa_elder_health --max-pages 30
uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
"""

from __future__ import annotations

import argparse
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from kinsun import tracing
from kinsun.db import Database, ensure_schema
from kinsun.rag.crawler import CrawlerConfig, HealthEducationCrawler
from kinsun.rag.embeddings import build_embedding_model
from kinsun.rag.evaluation import evaluate_golden_set, load_golden_set
from kinsun.rag.ingestion import (
    IngestionPipeline,
    group_seed_documents_by_source,
    load_seed_documents,
)
from kinsun.rag.releases import PgRagReleaseStore, QualityGateInput
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.schemas import RAG_EMBEDDING_DIMENSIONS, ContentPolicy
from kinsun.rag.source_registry import SourceRegistry, order_answer_first
from kinsun.rag.source_validator import SourceValidator
from kinsun.rag.vector_store import PgVectorStore


@tracing.track(name="rag_ingest", type="general", capture_input=False, capture_output=True)
def main() -> None:
    _load_dotenv(Path(".env"))
    args = _parse_args()
    database_url = _require_env("DATABASE_URL")
    embedding_backend = os.environ.get("RAG_EMBEDDING_BACKEND", "gemini")
    # 地端不需要金鑰；雲端才強制要求，避免只想跑地端的人被卡住。
    gemini_api_key = "" if embedding_backend == "local" else _require_env("GEMINI_API_KEY")
    embedding_model = os.environ.get("RAG_EMBEDDING_MODEL", "gemini-embedding-001")
    content_policy = ContentPolicy(os.environ.get("RAG_CONTENT_POLICY", "allowed_only"))
    ensure_schema(database_url)
    db = Database.open_for_cli(database_url)
    try:
        store = PgVectorStore(db)
        if args.reset:
            store.reset()
        index_version = args.index_version or datetime.now(UTC).strftime("rag-%Y%m%dT%H%M%SZ")
        releases = PgRagReleaseStore(db)
        releases.begin_release(
            index_version,
            embedding_model=embedding_model,
            content_policy=content_policy,
        )
        embedder = build_embedding_model(
            backend=embedding_backend,
            model=embedding_model,
            dimensions=RAG_EMBEDDING_DIMENSIONS,
            request_timeout_seconds=args.embedding_timeout,
            batch_size=args.embedding_batch_size,
            endpoint=os.environ.get("RAG_EMBEDDING_ENDPOINT", ""),
            local_api_key=os.environ.get("RAG_EMBEDDING_API_KEY", ""),
            gemini_api_key=gemini_api_key,
            request_delay_seconds=args.embedding_delay,
            max_retries=args.embedding_retries,
            retry_initial_delay_seconds=args.embedding_retry_initial_delay,
            retry_max_delay_seconds=args.embedding_retry_max_delay,
        )
        pipeline = IngestionPipeline(
            store=store,
            embedding_model=embedder,
            max_chunk_chars=args.max_chunk_chars,
        )
        registry = SourceRegistry()
        # ANSWER 先於 DISCOVERY：跨來源 URL 去重是先到先得，順序決定衛教內文
        # 會不會被只留 membership 的 discovery 來源搶走（見 order_answer_first）。
        source_ids = order_answer_first(
            args.source or [source.source_id for source in registry.approved_for_rag()],
            registry,
        )
        try:
            _ingest_seed_file(
                args,
                registry,
                pipeline,
                source_ids,
                content_policy,
                index_version,
            )
            if not args.no_crawl:
                _crawl_and_ingest(
                    args,
                    registry,
                    pipeline,
                    source_ids,
                    content_policy,
                    index_version,
                    store,
                )
            _evaluate_and_publish(
                db,
                releases,
                embedder,
                index_version=index_version,
                golden_set=Path(args.golden_set),
            )
        except Exception as exc:
            release = releases.get(index_version)
            if release is not None and release.status.value in {"building", "candidate"}:
                releases.mark_failed(index_version, error_message=str(exc))
            raise
    finally:
        db.close()


def _ingest_seed_file(
    args,
    registry,
    pipeline,
    source_ids: tuple[str, ...],
    content_policy: ContentPolicy,
    index_version: str,
) -> None:
    if args.input is None:
        return
    documents = load_seed_documents(Path(args.input))
    grouped = group_seed_documents_by_source(documents)
    for source_id, rows in grouped.items():
        if source_id not in source_ids:
            continue
        source = registry.get(source_id)
        validation = SourceValidator(content_policy=content_policy).validate(source)
        if not validation.can_ingest:
            print(f"[skip] {source_id}: {'; '.join(validation.issues)}")
            continue
        pipeline.ingest_seed_documents(
            source,
            rows,
            operator_or_job_id=index_version,
            index_version=index_version,
        )
        print(f"[seed] {source_id}: {len(rows)} documents")


def _crawl_and_ingest(
    args,
    registry,
    pipeline,
    source_ids: tuple[str, ...],
    content_policy: ContentPolicy,
    index_version: str,
    store: PgVectorStore,
) -> None:
    validator = SourceValidator(content_policy=content_policy)
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(
            max_pages_per_source=args.max_pages,
            delay_seconds=args.delay,
            timeout_seconds=args.timeout,
            retries=args.retries,
        )
    )
    for source_id in source_ids:
        source = registry.get(source_id)
        validation = validator.validate(source)
        if not validation.can_ingest:
            print(f"[skip] {source_id}: {'; '.join(validation.issues)}")
            continue
        # 有 sitemap 就讀清單，沒有才退回爬連結。爬連結在每頁都渲染全站選單的
        # 網站上必然主題漂移（2026-08-01 實測，見 Source.sitemap_url 的註解）。
        result = crawler.crawl_sitemap(source) if source.sitemap_url else crawler.crawl(source)
        admitted = pipeline.ingest_pages(
            source,
            result.pages,
            operator_or_job_id=index_version,
            index_version=index_version,
        )
        for url, message in result.failed_urls:
            store.log_ingestion(
                source_id=source_id,
                url=url,
                fetched_at=datetime.now(UTC).timestamp(),
                content_hash=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                chunk_count=0,
                parser_used="crawler",
                status="failed",
                error_message=message,
                operator_or_job_id=index_version,
            )
        print(
            f"[crawl] {source_id}: pages={len(result.pages)} 收錄={len(admitted)} "
            f"未收錄={len(result.pages) - len(admitted)} "
            f"failed={len(result.failed_urls)} skipped={len(result.skipped_urls)}"
        )


def _evaluate_and_publish(
    db: Database,
    releases: PgRagReleaseStore,
    embedder,
    *,
    index_version: str,
    golden_set: Path,
) -> None:
    audit = db.query_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE status IN ('success','failed')),
            COUNT(*) FILTER (WHERE status='failed')
        FROM rag_ingestion_audit_logs
        WHERE operator_or_job_id=%s
        """,
        (index_version,),
    ) or (0, 0)
    retriever = HealthEducationRetriever(
        vector_store=PgVectorStore(db, index_version=index_version),
        embedding_model=embedder,
    )
    report = evaluate_golden_set(retriever, load_golden_set(golden_set))
    result = releases.evaluate_and_publish(
        index_version,
        QualityGateInput(
            attempted_documents=int(audit[0]),
            failed_documents=int(audit[1]),
            safety_pass_rate=report.safety_pass_rate,
            supported_top3_recall=report.supported_top3_recall,
            unsupported_false_positive_rate=report.unsupported_false_positive_rate,
            citation_correctness=report.citation_correctness,
            relevance_threshold=report.threshold,
        ),
    )
    if not result.passed:
        raise RuntimeError(f"release 品質閘門失敗：{'；'.join(result.failures)}")
    print(f"[published] {index_version}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KinSun 衛教 RAG crawler／ingestion")
    parser.add_argument("--source", action="append", help="指定 source_id；可重複指定")
    parser.add_argument("--input", help="JSONL seed 文件路徑")
    parser.add_argument("--no-crawl", action="store_true", help="只匯入 --input，不啟動 crawler")
    parser.add_argument("--reset", action="store_true", help="先清空 RAG 文件與 chunk")
    parser.add_argument("--index-version", help="自訂 release 版本名稱")
    parser.add_argument("--golden-set", default="data/rag/golden_set.jsonl")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=_env_int("RAG_CRAWLER_MAX_PAGES", 20),
        help="每個來源最多爬取頁數",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=_env_float("RAG_CRAWLER_DELAY_SECONDS", 2.0),
        help="每頁之間的秒數",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout 秒數")
    parser.add_argument("--retries", type=int, default=2, help="單頁重試次數")
    parser.add_argument("--max-chunk-chars", type=int, default=700, help="chunk 最大字數")
    parser.add_argument(
        "--embedding-delay",
        type=float,
        default=_env_float("RAG_EMBEDDING_DELAY_SECONDS", 6.0),
        help="Gemini embedding 每次呼叫前等待秒數",
    )
    parser.add_argument(
        "--embedding-retries",
        type=int,
        default=_env_int("RAG_EMBEDDING_RETRIES", 5),
        help="Gemini embedding 429／暫時性錯誤重試次數",
    )
    parser.add_argument(
        "--embedding-retry-initial-delay",
        type=float,
        default=_env_float("RAG_EMBEDDING_RETRY_INITIAL_DELAY_SECONDS", 30.0),
        help="Gemini embedding 第一次重試等待秒數",
    )
    parser.add_argument(
        "--embedding-retry-max-delay",
        type=float,
        default=_env_float("RAG_EMBEDDING_RETRY_MAX_DELAY_SECONDS", 300.0),
        help="Gemini embedding 重試等待秒數上限",
    )
    parser.add_argument(
        "--embedding-timeout",
        type=float,
        default=_env_float("RAG_EMBEDDING_TIMEOUT_SECONDS", 60.0),
        help="單次 embedding HTTP 呼叫逾時秒數",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=_env_int("RAG_EMBEDDING_BATCH_SIZE", 20),
        help="gemini-embedding-001 每次同步批次的 chunk 數",
    )
    args = parser.parse_args()
    if args.max_pages <= 0:
        parser.error("--max-pages 必須大於 0")
    if args.delay < 0:
        parser.error("--delay 不可小於 0")
    if args.timeout <= 0:
        parser.error("--timeout 必須大於 0")
    if args.retries < 0:
        parser.error("--retries 不可小於 0")
    if not 80 <= args.max_chunk_chars <= 700:
        parser.error("--max-chunk-chars 必須介於 80 到 700")
    if args.embedding_delay < 0:
        parser.error("--embedding-delay 不可小於 0")
    if args.embedding_retries < 0:
        parser.error("--embedding-retries 不可小於 0")
    if args.embedding_retry_initial_delay < 0:
        parser.error("--embedding-retry-initial-delay 不可小於 0")
    if args.embedding_retry_max_delay < 0:
        parser.error("--embedding-retry-max-delay 不可小於 0")
    if args.embedding_timeout <= 0:
        parser.error("--embedding-timeout 必須大於 0")
    if args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size 必須大於 0")
    return args


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"缺少必要環境變數：{key}")
    return value


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{key} 必須是整數") from exc


def _env_float(key: str, default: float) -> float:
    value = os.environ.get(key)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{key} 必須是數字") from exc


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    main()
