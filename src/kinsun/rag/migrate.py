"""從舊 RAG 文件庫唯讀重切、重嵌入到版本化專案庫。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from kinsun.config import load_dotenv
from kinsun.db import Database, ensure_schema
from kinsun.rag.embeddings import build_embedding_model
from kinsun.rag.evaluation import evaluate_golden_set, load_golden_set
from kinsun.rag.ingestion import IngestionPipeline, deduplicate_documents, normalize_url
from kinsun.rag.releases import PgRagReleaseStore, QualityGateInput
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.schemas import (
    RAG_EMBEDDING_DIMENSIONS,
    Audience,
    ContentPolicy,
    CopyrightStatus,
    Language,
    MedicalScope,
    RagDocument,
    SourceType,
    TrustLevel,
)
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator
from kinsun.rag.text_cleaner import clean_text
from kinsun.rag.vector_store import PgVectorStore


def main() -> None:
    load_dotenv()
    args = _parse_args()
    target_url = _require_env("DATABASE_URL") if args.in_place else ""
    source_url = target_url if args.in_place else _require_env("RAG_SOURCE_DATABASE_URL")
    content_policy = ContentPolicy(os.environ.get("RAG_CONTENT_POLICY", "allowed_only"))
    documents, backup_records = _read_source_documents(source_url)
    report = _dry_run_report(documents, content_policy=content_policy)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        return

    if not args.in_place:
        target_url = _require_env("DATABASE_URL")
    if not args.in_place and _same_database(source_url, target_url):
        raise RuntimeError("RAG_SOURCE_DATABASE_URL 不得與 DATABASE_URL 相同。")
    api_key = _require_env("GEMINI_API_KEY")
    model_name = os.environ.get("RAG_EMBEDDING_MODEL", "gemini-embedding-001")
    index_version = args.index_version or datetime.now(UTC).strftime("rag-%Y%m%dT%H%M%SZ")
    if args.in_place:
        backup_path = _write_backup(
            backup_records,
            backup_dir=Path(args.backup_dir).expanduser(),
            index_version=index_version,
        )
        print(f"[backup] {backup_path}")
    ensure_schema(target_url)
    db = Database.open_for_cli(target_url)
    try:
        _build_release(
            db,
            documents,
            index_version=index_version,
            model_name=model_name,
            api_key=api_key,
            content_policy=content_policy,
            golden_set=Path(args.golden_set),
            args=args,
        )
    finally:
        db.close()


def _build_release(
    db: Database,
    documents: tuple[RagDocument, ...],
    *,
    index_version: str,
    model_name: str,
    api_key: str,
    content_policy: ContentPolicy,
    golden_set: Path,
    args: argparse.Namespace,
) -> None:
    release_store = PgRagReleaseStore(db)
    release_store.begin_release(
        index_version,
        embedding_model=model_name,
        content_policy=content_policy,
    )
    # 走同一個工廠：維度必須與 rag_chunks.embedding 一致，寫入端各自建構會漏改。
    embedder = build_embedding_model(
        backend=os.environ.get("RAG_EMBEDDING_BACKEND", "gemini"),
        model=model_name,
        dimensions=RAG_EMBEDDING_DIMENSIONS,
        request_timeout_seconds=args.embedding_timeout,
        batch_size=args.embedding_batch_size,
        endpoint=os.environ.get("RAG_EMBEDDING_ENDPOINT", ""),
        local_api_key=os.environ.get("RAG_EMBEDDING_API_KEY", ""),
        gemini_api_key=api_key,
        request_delay_seconds=args.embedding_delay,
        max_retries=args.embedding_retries,
        retry_initial_delay_seconds=args.embedding_retry_initial_delay,
        retry_max_delay_seconds=args.embedding_retry_max_delay,
    )
    store = PgVectorStore(db)
    pipeline = IngestionPipeline(store=store, embedding_model=embedder, max_chunk_chars=700)
    registry = SourceRegistry()
    validator = SourceValidator(content_policy=content_policy)
    kept_documents, discarded_documents = deduplicate_documents(documents)
    store.log_skipped_documents(
        discarded_documents,
        fetched_at=datetime.now(UTC).timestamp(),
        parser_used="deduplication",
        operator_or_job_id=index_version,
    )
    grouped: dict[str, list[RagDocument]] = defaultdict(list)
    for document in kept_documents:
        grouped[document.source_id].append(document)

    attempted = 0
    try:
        for source_id, rows in grouped.items():
            try:
                source = registry.get(source_id)
            except KeyError:
                print(f"[skip] 未登錄來源：{source_id}")
                continue
            validation = validator.validate(source)
            if not validation.can_ingest:
                print(f"[skip] {source_id}: {'; '.join(validation.issues)}")
                continue
            attempted += len(rows)
            pipeline.ingest_documents(
                source,
                tuple(rows),
                operator_or_job_id=index_version,
                index_version=index_version,
            )

        audit = db.query_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE status='failed'),
                COUNT(*) FILTER (WHERE status='success')
            FROM rag_ingestion_audit_logs
            WHERE operator_or_job_id=%s
            """,
            (index_version,),
        ) or (0, 0)
        failed_documents = int(audit[0] or 0)
        evaluator = HealthEducationRetriever(
            vector_store=PgVectorStore(db, index_version=index_version),
            embedding_model=embedder,
        )
        golden_report = evaluate_golden_set(evaluator, load_golden_set(golden_set))
        result = release_store.evaluate_and_publish(
            index_version,
            QualityGateInput(
                attempted_documents=attempted,
                failed_documents=failed_documents,
                safety_pass_rate=golden_report.safety_pass_rate,
                supported_top3_recall=golden_report.supported_top3_recall,
                unsupported_false_positive_rate=golden_report.unsupported_false_positive_rate,
                citation_correctness=golden_report.citation_correctness,
                relevance_threshold=golden_report.threshold,
            ),
        )
        if not result.passed:
            raise RuntimeError(f"release 品質閘門失敗：{'；'.join(result.failures)}")
        print(f"[published] {index_version}")
    except Exception as exc:
        release = release_store.get(index_version)
        if release is not None and release.status.value in {"building", "candidate"}:
            release_store.mark_failed(index_version, error_message=str(exc))
        raise


def _read_source_documents(
    database_url: str,
) -> tuple[tuple[RagDocument, ...], tuple[dict[str, object], ...]]:
    """在同一個唯讀快照載入遷移文件與可忠實回復的原始備份紀錄。"""
    with psycopg.connect(database_url) as conn, conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            """
            SELECT document_id, source_id, url, title, publisher, text, content_hash,
                   source_type, language, topic, audience, medical_scope, trust_level,
                   copyright_status, published_at, updated_at, retrieved_at
            FROM rag_documents
            """
        ).fetchall()
    return (
        tuple(_row_to_document(row) for row in rows),
        tuple(_row_to_backup_record(row) for row in rows),
    )


def _row_to_document(row: tuple) -> RagDocument:
    cleaned = clean_text(str(row[5]))
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    return RagDocument(
        document_id=f"{row[1]}:{content_hash[:24]}",
        source_id=str(row[1]),
        url=normalize_url(str(row[2])),
        title=str(row[3]),
        publisher=str(row[4]),
        text=cleaned,
        content_hash=content_hash,
        source_type=SourceType(row[7]),
        language=Language(row[8]),
        topic=str(row[9]),
        audience=Audience(row[10]),
        medical_scope=MedicalScope(row[11]),
        trust_level=TrustLevel(row[12]),
        copyright_status=CopyrightStatus(row[13]),
        published_at=_as_date(row[14]),
        updated_at=_as_date(row[15]),
        retrieved_at=_as_date(row[16]) or date.today(),
    )


def _dry_run_report(
    documents: tuple[RagDocument, ...],
    *,
    content_policy: ContentPolicy = ContentPolicy.ALLOWED_ONLY,
) -> dict[str, object]:
    kept, discarded = deduplicate_documents(documents)
    registry = SourceRegistry()
    validator = SourceValidator(content_policy=content_policy)
    source_ids = {document.source_id for document in documents}
    by_source: dict[str, dict[str, int]] = {
        source_id: {"kept": 0, "discarded": 0} for source_id in source_ids
    }
    for document in kept:
        by_source[document.source_id]["kept"] += 1
    for document, _ in discarded:
        by_source[document.source_id]["discarded"] += 1
    role_counts = {"answer": 0, "discovery": 0}
    skipped_sources: dict[str, tuple[str, ...]] = {}
    eligible_document_count = 0
    for source_id, rows in _group_documents(kept).items():
        try:
            source = registry.get(source_id)
        except KeyError:
            skipped_sources[source_id] = ("來源未登錄",)
            continue
        validation = validator.validate(source)
        if not validation.can_ingest:
            skipped_sources[source_id] = validation.issues
            continue
        eligible_document_count += len(rows)
        role_counts[source.role.value] += len(rows)
    return {
        "source_document_count": len(documents),
        "candidate_document_count": len(kept),
        "eligible_document_count": eligible_document_count,
        "discarded_document_count": len(discarded),
        "content_policy": content_policy.value,
        "answer_document_count": role_counts["answer"],
        "discovery_document_count": role_counts["discovery"],
        "skipped_sources": skipped_sources,
        "by_source": by_source,
    }


def _group_documents(documents: tuple[RagDocument, ...]) -> dict[str, list[RagDocument]]:
    grouped: dict[str, list[RagDocument]] = defaultdict(list)
    for document in documents:
        grouped[document.source_id].append(document)
    return grouped


def _write_backup(
    records: tuple[dict[str, object], ...],
    *,
    backup_dir: Path,
    index_version: str,
) -> Path:
    """在任何 DB 寫入前，將來源文件備份為 gzip JSONL 並留下 checksum manifest。"""
    safe_version = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_" for char in index_version
    )
    destination = backup_dir / safe_version
    destination.mkdir(parents=True, exist_ok=False)
    backup_path = destination / "rag_documents.jsonl.gz"
    temporary_backup = destination / ".rag_documents.jsonl.gz.tmp"
    try:
        with gzip.open(temporary_backup, "wt", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
        temporary_backup.replace(backup_path)
        _restrict_permissions(backup_path)
        checksum = _file_sha256(backup_path)
        manifest = {
            "backup_file": backup_path.name,
            "created_at": datetime.now(UTC).isoformat(),
            "document_count": len(records),
            "format": "kinsun-rag-documents-raw-jsonl-gzip-v1",
            "index_version": index_version,
            "sha256": checksum,
        }
        manifest_path = destination / "manifest.json"
        temporary_manifest = destination / ".manifest.json.tmp"
        temporary_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)
        _restrict_permissions(manifest_path)
    except Exception:
        temporary_backup.unlink(missing_ok=True)
        raise
    return backup_path


def _row_to_backup_record(row: tuple) -> dict[str, object]:
    """保留舊表原值，避免正規化後的資料無法作首次遷移回復。"""
    return {
        "document_id": str(row[0]),
        "source_id": str(row[1]),
        "url": str(row[2]),
        "title": str(row[3]),
        "publisher": str(row[4]),
        "text": str(row[5]),
        "content_hash": str(row[6]),
        "source_type": str(row[7]),
        "language": str(row[8]),
        "topic": str(row[9]),
        "audience": str(row[10]),
        "medical_scope": str(row[11]),
        "trust_level": str(row[12]),
        "copyright_status": str(row[13]),
        "published_at": _date_to_iso(row[14]),
        "updated_at": _date_to_iso(row[15]),
        "retrieved_at": _date_to_iso(row[16]),
    }


def _date_to_iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # Windows ACL 不一定支援 POSIX mode；備份仍位於使用者自己的資料夾。
        pass


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG 個人庫到專案庫的版本化遷移")
    parser.add_argument("--dry-run", action="store_true", help="只讀來源並輸出去重報告")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="以 DATABASE_URL 作來源與目標；正式寫入前自動備份來源文件",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(Path.home() / ".kinsun" / "backups" / "rag"),
        help="原地遷移備份根目錄",
    )
    parser.add_argument("--index-version", help="自訂 release 版本名稱")
    parser.add_argument("--golden-set", default="data/rag/golden_set.jsonl")
    parser.add_argument(
        "--embedding-delay",
        type=float,
        default=float(os.environ.get("RAG_EMBEDDING_DELAY_SECONDS", "6")),
    )
    parser.add_argument(
        "--embedding-retries",
        type=int,
        default=int(os.environ.get("RAG_EMBEDDING_RETRIES", "5")),
    )
    parser.add_argument(
        "--embedding-timeout",
        type=float,
        default=float(os.environ.get("RAG_EMBEDDING_TIMEOUT_SECONDS", "60")),
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=int(os.environ.get("RAG_EMBEDDING_BATCH_SIZE", "20")),
    )
    parser.add_argument(
        "--embedding-retry-initial-delay",
        type=float,
        default=float(os.environ.get("RAG_EMBEDDING_RETRY_INITIAL_DELAY_SECONDS", "30")),
    )
    parser.add_argument(
        "--embedding-retry-max-delay",
        type=float,
        default=float(os.environ.get("RAG_EMBEDDING_RETRY_MAX_DELAY_SECONDS", "300")),
    )
    args = parser.parse_args()
    if args.embedding_delay < 0:
        parser.error("--embedding-delay 不可小於 0")
    if args.embedding_retries < 0:
        parser.error("--embedding-retries 不可小於 0")
    if args.embedding_timeout <= 0:
        parser.error("--embedding-timeout 必須大於 0")
    if args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size 必須大於 0")
    if args.embedding_retry_initial_delay < 0:
        parser.error("--embedding-retry-initial-delay 不可小於 0")
    if args.embedding_retry_max_delay < 0:
        parser.error("--embedding-retry-max-delay 不可小於 0")
    return args


def _require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"缺少必要環境變數：{key}")
    return value


def _same_database(left: str, right: str) -> bool:
    left_info = conninfo_to_dict(left)
    right_info = conninfo_to_dict(right)

    def identity(info: dict[str, str]) -> tuple[str, str, str]:
        host = info.get("hostaddr") or info.get("host") or "localhost"
        return host.lower(), info.get("port", "5432"), info.get("dbname", "")

    return identity(left_info) == identity(right_info)


if __name__ == "__main__":
    main()
