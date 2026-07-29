"""RAG release 查詢、rollback 與清理 CLI。"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from kinsun.config import load_dotenv
from kinsun.db import Database, ensure_schema
from kinsun.rag.releases import PgRagReleaseStore


def main() -> None:
    load_dotenv()
    args = _parse_args()
    database_url = _require_env("DATABASE_URL")
    ensure_schema(database_url)
    db = Database.open_for_cli(database_url)
    try:
        store = PgRagReleaseStore(db)
        if args.command == "list":
            rows = [asdict(release) for release in store.list_releases(limit=args.limit)]
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        elif args.command == "rollback":
            store.rollback(args.index_version)
            print(f"[active] {args.index_version}")
        elif args.command == "cleanup":
            store.cleanup(audit_retention_days=args.audit_retention_days)
            print("[done] RAG releases 與稽核資料已依政策清理。")
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KinSun RAG release 管理")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="列出 releases")
    list_parser.add_argument("--limit", type=int, default=20)
    rollback = subparsers.add_parser("rollback", help="切回已發布版本")
    rollback.add_argument("index_version")
    cleanup = subparsers.add_parser("cleanup", help="保留 active 與前兩個成功版本")
    cleanup.add_argument(
        "--audit-retention-days",
        type=int,
        default=int(os.environ.get("RAG_AUDIT_RETENTION_DAYS", "90")),
    )
    args = parser.parse_args()
    if args.command == "list" and args.limit <= 0:
        parser.error("--limit 必須大於 0")
    if args.command == "cleanup" and args.audit_retention_days <= 0:
        parser.error("--audit-retention-days 必須大於 0")
    return args


def _require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"缺少必要環境變數：{key}")
    return value


if __name__ == "__main__":
    main()
