import gzip
import hashlib
import json
import sys

import kinsun.rag.migrate as migrate
from kinsun.rag.migrate import (
    _dry_run_report,
    _row_to_backup_record,
    _row_to_document,
    _same_database,
    _write_backup,
)


def test_same_database_ignores_credentials_and_explicit_default_port():
    assert _same_database(
        "postgresql://reader:source@db.example.com/project",
        "postgresql://writer:target@db.example.com:5432/project",
    )


def test_same_database_distinguishes_database_and_host():
    source = "postgresql://reader:source@source.example.com/project"

    assert not _same_database(source, "postgresql://writer:target@target.example.com/project")
    assert not _same_database(source, "postgresql://writer:target@source.example.com/other")


def test_dry_run_deduplicates_same_content_across_sources():
    base = (
        "document-id",
        "hpa_elder_health",
        "http://example.test/long/path",
        "衛教",
        "國民健康署",
        "相同衛教內容。",
        "舊 hash",
        "government",
        "zh-TW",
        "一般衛教",
        "general_public",
        "health_education",
        "high",
        "allowed",
        None,
        None,
        None,
    )
    first = _row_to_document(base)
    second = _row_to_document(
        (
            "other-id",
            "mohw_health_article",
            "https://example.test/a",
            *base[3:],
        )
    )

    report = _dry_run_report((first, second))

    assert report["candidate_document_count"] == 1
    assert report["discarded_document_count"] == 1


def test_migrate_dry_run_does_not_require_or_initialize_target(monkeypatch, capsys):
    monkeypatch.setenv("RAG_SOURCE_DATABASE_URL", "postgresql://reader@source/source")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["migrate", "--dry-run"])
    monkeypatch.setattr(migrate, "load_dotenv", lambda: None)
    monkeypatch.setattr(migrate, "_read_source_documents", lambda _: ((), ()))
    monkeypatch.setattr(
        migrate,
        "ensure_schema",
        lambda _: (_ for _ in ()).throw(AssertionError("dry-run 不可初始化目標 DB")),
    )

    migrate.main()

    assert '"source_document_count": 0' in capsys.readouterr().out


def test_in_place_dry_run_only_requires_database_url(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://writer@personal/project")
    monkeypatch.delenv("RAG_SOURCE_DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["migrate", "--in-place", "--dry-run"])
    monkeypatch.setattr(migrate, "load_dotenv", lambda: None)
    monkeypatch.setattr(migrate, "_read_source_documents", lambda _: ((), ()))
    monkeypatch.setattr(
        migrate,
        "ensure_schema",
        lambda _: (_ for _ in ()).throw(AssertionError("dry-run 不可初始化目標 DB")),
    )
    monkeypatch.setattr(
        migrate,
        "_write_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dry-run 不可建立備份")),
    )

    migrate.main()

    assert '"source_document_count": 0' in capsys.readouterr().out


def test_write_backup_creates_gzip_jsonl_and_checksum_manifest(tmp_path):
    row = (
        "old-id",
        "hpa_elder_health",
        "https://example.test/health#section",
        "長者衛教",
        "國民健康署",
        "  每天適度活動。  ",
        "old-hash",
        "government",
        "zh-TW",
        "高齡健康",
        "elder",
        "health_education",
        "high",
        "allowed",
        None,
        None,
        None,
    )
    record = _row_to_backup_record(row)

    backup = _write_backup((record,), backup_dir=tmp_path, index_version="rag:test")

    manifest = json.loads((backup.parent / "manifest.json").read_text(encoding="utf-8"))
    with gzip.open(backup, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert rows[0]["text"] == "  每天適度活動。  "
    assert rows[0]["document_id"] == "old-id"
    assert rows[0]["content_hash"] == "old-hash"
    assert rows[0]["url"] == "https://example.test/health#section"
    assert manifest["document_count"] == 1
    assert manifest["format"] == "kinsun-rag-documents-raw-jsonl-gzip-v1"
    assert manifest["index_version"] == "rag:test"
    assert manifest["sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
