"""合約測試共用夾具。

- `ns`：每個測試獨立的識別字前綴，讓合約能在同一庫上以成員關係斷言、互不干擾。
- `pg_database`：連**獨立測試庫**（✅ D-69，甲-7）——`KINSUN_IT=1` 且設
  `KINSUN_TEST_DATABASE_URL` 才跑，否則整批 skip；嚴禁與 `DATABASE_URL` 相同
  （防呆：整合測試不再直寫正式庫）。session 開始時清空全部資料表（測試庫專用，
  安全）；結束不清，失敗現場保留供排查。

本機測試庫（DGX 一行起，含 pgvector）：
  docker run -d --name kinsun-test-pg -p 5433:5432 \
    -e POSTGRES_PASSWORD=kinsun-test pgvector/pgvector:pg17
  KINSUN_IT=1 \
  KINSUN_TEST_DATABASE_URL=postgresql://postgres:kinsun-test@localhost:5433/postgres \
  uv run pytest
"""

from __future__ import annotations

import os
import uuid

import pytest


@pytest.fixture
def ns() -> str:
    return f"ct-{uuid.uuid4().hex[:8]}-"


def _truncate_all_tables(db) -> None:
    """清空 public schema 全部資料表（獨立測試庫專用；每個 session 從乾淨狀態開始）。"""
    rows = db.query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    tables = [row[0] for row in rows]
    if tables:
        joined = ", ".join(f'"{t}"' for t in tables)
        db.execute(f"TRUNCATE TABLE {joined} CASCADE")


def _resolve_test_db_url() -> str:
    """取得獨立測試庫 URL；未啟用／未設定則 skip，指到正式庫則直接終止。"""
    if os.environ.get("KINSUN_IT") != "1":
        pytest.skip("需 KINSUN_IT=1 與 KINSUN_TEST_DATABASE_URL（連獨立測試庫）")
    url = os.environ.get("KINSUN_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("未設 KINSUN_TEST_DATABASE_URL——整合測試不再直連 DATABASE_URL 正式庫（D-69）")
    if url == os.environ.get("DATABASE_URL", ""):
        pytest.exit("KINSUN_TEST_DATABASE_URL 不可與 DATABASE_URL 相同——禁止寫正式庫（D-69）")
    return url


@pytest.fixture(scope="session")
def pg_url() -> str:
    """獨立測試庫連線串（供需要自行開連線的整合測試用）。"""
    return _resolve_test_db_url()


@pytest.fixture(scope="session")
def pg_database():
    url = _resolve_test_db_url()
    from kinsun.db import Database, ensure_schema

    ensure_schema(url)
    db = Database.open(url)
    _truncate_all_tables(db)
    yield db
    db.close()
