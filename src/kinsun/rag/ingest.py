"""衛教 RAG ingestion CLI。

範例：
uv run python -m kinsun.rag.ingest --source hpa_elder_health --max-pages 30
uv run python -m kinsun.rag.ingest --input data/rag/demo_seed.jsonl --no-crawl
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from kinsun.db import Database, ensure_schema
from kinsun.rag.crawler import CrawlerConfig, HealthEducationCrawler
from kinsun.rag.embeddings import GeminiEmbeddingModel
from kinsun.rag.ingestion import (
    IngestionPipeline,
    group_seed_documents_by_source,
    load_seed_documents,
)
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator
from kinsun.rag.vector_store import PgVectorStore


def main() -> None:
    args = _parse_args()
    _load_dotenv(Path(".env"))
    database_url = _require_env("DATABASE_URL")
    gemini_api_key = _require_env("GEMINI_API_KEY")
    embedding_model = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
    ensure_schema(database_url)
    db = Database.open(database_url)
    try:
        store = PgVectorStore(db)
        if args.reset:
            store.reset()
        embedder = GeminiEmbeddingModel(
            api_key=gemini_api_key,
            model=embedding_model,
        )
        pipeline = IngestionPipeline(
            store=store,
            embedding_model=embedder,
            max_chunk_chars=args.max_chunk_chars,
        )
        registry = SourceRegistry()
        source_ids = tuple(
            args.source or [source.source_id for source in registry.approved_for_rag()]
        )
        _ingest_seed_file(args, registry, pipeline, source_ids)
        if not args.no_crawl:
            _crawl_and_ingest(args, registry, pipeline, source_ids)
    finally:
        db.close()


def _ingest_seed_file(args, registry, pipeline, source_ids: tuple[str, ...]) -> None:
    if args.input is None:
        return
    documents = load_seed_documents(Path(args.input))
    grouped = group_seed_documents_by_source(documents)
    for source_id, rows in grouped.items():
        if source_id not in source_ids:
            continue
        source = registry.get(source_id)
        pipeline.ingest_seed_documents(
            source,
            rows,
            operator_or_job_id=args.job_id,
        )
        print(f"[seed] {source_id}: {len(rows)} documents")


def _crawl_and_ingest(args, registry, pipeline, source_ids: tuple[str, ...]) -> None:
    validator = SourceValidator()
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
        result = crawler.crawl(source)
        pipeline.ingest_pages(source, result.pages, operator_or_job_id=args.job_id)
        print(
            f"[crawl] {source_id}: pages={len(result.pages)} "
            f"failed={len(result.failed_urls)} skipped={len(result.skipped_urls)}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KinSun 衛教 RAG crawler／ingestion")
    parser.add_argument("--source", action="append", help="指定 source_id；可重複指定")
    parser.add_argument("--input", help="JSONL seed 文件路徑")
    parser.add_argument("--no-crawl", action="store_true", help="只匯入 --input，不啟動 crawler")
    parser.add_argument("--reset", action="store_true", help="先清空 RAG 文件與 chunk")
    parser.add_argument("--max-pages", type=int, default=80, help="每個來源最多爬取頁數")
    parser.add_argument("--delay", type=float, default=0.5, help="每頁之間的秒數")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout 秒數")
    parser.add_argument("--retries", type=int, default=2, help="單頁重試次數")
    parser.add_argument("--max-chunk-chars", type=int, default=700, help="chunk 最大字數")
    parser.add_argument("--job-id", default="manual", help="寫入 audit log 的 job/operator id")
    return parser.parse_args()


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"缺少必要環境變數：{key}")
    return value


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
