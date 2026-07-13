"""合約測試共用夾具。

- `ns`：每個測試獨立的識別字前綴，讓合約能在同一庫上以成員關係斷言、互不干擾。
- `pg_database`：連**獨立測試庫**（✅ D-69，甲-7）——`KINSUN_IT=1` 且設
  `KINSUN_TEST_DATABASE_URL` 才跑；嚴禁與 `DATABASE_URL` 相同（防呆：整合測試
  不再直寫正式庫）。session 開始時清空全部資料表（測試庫專用，安全）；結束不清，
  失敗現場保留供排查。

本機測試庫：`scripts/test_db.sh up`（Docker 起 pgvector，與 CI 同一組設定）。
兩個鍵已寫在 `.env`，`load_dotenv` 會補進環境變數，直接 `uv run pytest` 即可。

設了 `KINSUN_IT=1` 卻連不上測試庫時**故意讓測試紅**、不 skip：整合測試靜默跳過
正是庚-07 遷移缺陷溜到正式庫才爆的原因（見 tests/test_pg_db.py）。要暫時關掉整批
Pg 測試，把 .env 的 KINSUN_IT 改成 0。
"""

from __future__ import annotations

import os
import uuid

import pytest

from kinsun.accounts import passwords as _passwords
from kinsun.config import load_dotenv

# 讓 .env 的 KINSUN_IT／KINSUN_TEST_DATABASE_URL 生效（只補缺、不覆蓋——CI 以真實
# 環境變數帶入，優先於 .env）。重用 config 的實作，不引入 python-dotenv。
load_dotenv()

# 測試加速（✅ 庚-20）：生產 scrypt N=2**17（單次 ~200ms），測試裡雜湊呼叫上百次
# 會拖慢全套。此處降回 2**14——參數隨值存，驗證邏輯不受影響；
# 生產預設值由 test_accounts_passwords.py 以 PROD_SCRYPT_N 專測把關。
_passwords._N = 2**14


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


_UNREACHABLE_HINT = (
    "連不上測試庫（{url}）：{error}\n\n"
    "  → 跑 scripts/test_db.sh up 起本機測試庫，再重跑 pytest。\n"
    "  → 這裡刻意不 skip：整合測試靜默跳過，正是庚-07 遷移缺陷溜到正式庫才爆的原因。\n"
    "  → 真的要暫時跳過整批 Pg 測試，把 .env 的 KINSUN_IT 改成 0。"
)

# 連線探測結果快取：整個 session 只探一次，不必每個 fixture 都重連。
_probe_error: str | None = None
_probed = False


def _probe(url: str) -> None:
    """確認測試庫真的可連；連不上就讓測試紅（附排除步驟），不 skip。"""
    global _probed, _probe_error
    if not _probed:
        import psycopg

        _probed = True
        try:
            with psycopg.connect(url, connect_timeout=5):
                pass
        except Exception as exc:  # noqa: BLE001 - 任何連線失敗都要轉成可讀提示
            _probe_error = f"{type(exc).__name__}: {exc}".strip()
    if _probe_error is not None:
        # 遮蔽連線串裡的密碼再顯示。
        safe = url
        if "@" in url and "://" in url:
            scheme, _, rest = url.partition("://")
            safe = f"{scheme}://***@{rest.partition('@')[2]}"
        pytest.fail(_UNREACHABLE_HINT.format(url=safe, error=_probe_error), pytrace=False)


def _resolve_test_db_url() -> str:
    """取得獨立測試庫 URL；未啟用則 skip，指到正式庫則直接終止，連不上則失敗。"""
    if os.environ.get("KINSUN_IT") != "1":
        pytest.skip("需 KINSUN_IT=1 與 KINSUN_TEST_DATABASE_URL（連獨立測試庫）")
    url = os.environ.get("KINSUN_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("未設 KINSUN_TEST_DATABASE_URL——整合測試不再直連 DATABASE_URL 正式庫（D-69）")
    if url == os.environ.get("DATABASE_URL", ""):
        pytest.exit("KINSUN_TEST_DATABASE_URL 不可與 DATABASE_URL 相同——禁止寫正式庫（D-69）")
    _probe(url)
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
