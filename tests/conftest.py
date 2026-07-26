"""合約測試共用夾具。

- `ns`：每個測試獨立的識別字前綴，讓合約能在同一庫上以成員關係斷言、互不干擾。
- `pg_database`：連**獨立測試庫**（✅ D-69，甲-7）——`KINSUN_IT=1` 且設
  `KINSUN_TEST_DATABASE_URL` 才跑；嚴禁與 `DATABASE_URL` 相同（防呆：整合測試
  不再直寫正式庫）。session 開始時清空全部資料表（測試庫專用，安全）；結束不清，
  失敗現場保留供排查。

本機測試庫：`scripts/test_db.sh up`（Docker 起 pgvector，與 CI 同一組設定）。
兩個鍵已寫在 `.env`，本檔會把它們補進環境變數，直接 `uv run pytest` 即可——
但**只有這兩個鍵**，其餘正式設定一律不進測試行程（見下方「測試行程密封」）。

設了 `KINSUN_IT=1` 卻連不上測試庫時**故意讓測試紅**、不 skip：整合測試靜默跳過
正是庚-07 遷移缺陷溜到正式庫才爆的原因（見 tests/test_pg_db.py）。要暫時關掉整批
Pg 測試，把 .env 的 KINSUN_IT 改成 0。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from kinsun.accounts import passwords as _passwords

# ── 測試行程密封（2026-07-27）────────────────────────────────────────────
#
# ⚠️ 原本這裡是無條件 `load_dotenv()`，把正式 `.env` 的 106 個鍵灌進測試行程：
# 正式 Supabase 連線串、LINE token、Gemini 金鑰、admin 金鑰全都在裡面。於是每個測試
# 都得自己記得覆寫，而**已經漏掉一個**——`test_app.py` 覆寫了 `TTS_BACKEND` 卻沒覆寫
# `ASR_BACKEND`，`build_app()` 在單元測試裡真的建出了指向正式 DGX 的 `DgxAsrClient`。
#
# 正確的界線不是「每個測試自己小心」，是「測試行程根本拿不到」。
# CI 本來就在沒有 .env 的環境跑全套且長期全綠（ci.yml 的 test job 一個 env 都沒設），
# 證明沒有任何測試真的需要正式金鑰；密封只是讓本機對齊 CI。
#
# 只放行兩把測試旗標，其餘一律不載入，並把可能來自開發者 shell 的同名變數一併清掉。
TEST_ONLY_KEYS = {"KINSUN_IT", "KINSUN_TEST_DATABASE_URL"}

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_env_file(path: Path) -> dict[str, str]:
    """讀 .env 形式的檔案成 dict，**不**寫進 os.environ（與 config.load_dotenv 的差別）。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


_DOTENV = _read_env_file(_REPO_ROOT / ".env")
_DOTENV_EXAMPLE = _read_env_file(_REPO_ROOT / ".env.example")

# 「這個應用會讀哪些鍵」的單一真實來源＝`.env.example`（AGENTS.md 要求每個鍵都列在那）。
# 用它當清單而不是人工維護第二份名單——否則日後新增金鑰會漏掉密封。
APP_ENV_KEYS = frozenset(_DOTENV_EXAMPLE) | frozenset(_DOTENV)

# 真正該擋的「正式值」＝ .env 有值、且與 .env.example 的預設不同的那些。
# ⚠️ 收尾檢查比對**值**而不是「鍵在不在」：應用本來就會合法地寫環境變數
# （`tracing.configure` 就把 OPIK_URL_OVERRIDE 等三把 setdefault 進 os.environ，
# 那是設定 opik SDK 的方式），值來自測試給的 Settings、不是正式設定。
# 只看鍵會把這種合法寫入誤判成洩漏，逼人去關掉守衛——那才是最糟的結果。
PRODUCTION_VALUES = {
    key: value
    for key, value in _DOTENV.items()
    if value and key not in TEST_ONLY_KEYS and _DOTENV_EXAMPLE.get(key) != value
}

for _key in APP_ENV_KEYS - TEST_ONLY_KEYS:
    os.environ.pop(_key, None)

# 測試旗標仍補進來（只補缺、不覆蓋——CI 以真實環境變數帶入，優先於 .env）。
for _key in TEST_ONLY_KEYS:
    if _key in _DOTENV:
        os.environ.setdefault(_key, _DOTENV[_key])


def _production_database_url() -> str:
    """正式庫 URL，供 D-69 防呆比對。

    ⚠️ 必須讀 .env 檔而不是 `os.environ`：密封之後 `DATABASE_URL` 已經不在環境變數裡，
    沿用 `os.environ.get("DATABASE_URL", "")` 會變成跟空字串比對——防呆看起來還在，
    實際上不再擋任何東西（`test_conftest_hermetic.py` 守住這條）。
    真實環境變數優先，供 CI 以 secret 覆寫。
    """
    return os.environ.get("DATABASE_URL", "") or _DOTENV.get("DATABASE_URL", "")


# 測試加速（✅ 庚-20）：生產 scrypt N=2**17（單次 ~200ms），測試裡雜湊呼叫上百次
# 會拖慢全套。此處降回 2**14——參數隨值存，驗證邏輯不受影響；
# 生產預設值由 test_accounts_passwords.py 以 PROD_SCRYPT_N 專測把關。
_passwords._N = 2**14


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001 - pytest hook 簽章
    """收尾檢查：整場測試跑完後，正式金鑰不得出現在環境變數裡。

    ⚠️ 為什麼要這一道，而不是只靠 `test_conftest_hermetic.py`：那份測試只擋得住
    **排在它之前**的汙染（pytest 依檔名順序收集，本專案未裝 pytest-randomly）。
    實際踩到的就是這種——`test_app.py` 排在它前面，`build_app()` 裡的 `load_dotenv()`
    把 106 個鍵灌回整個行程。本 hook 與順序無關，任何一支測試汙染都攔得到。

    只警告不改變 exitstatus 的做法在這裡不夠：靜默的洩漏正是這次要根治的東西，
    故直接讓整場測試紅。
    """
    leaked = sorted(key for key, value in PRODUCTION_VALUES.items() if os.environ.get(key) == value)
    if leaked:
        session.exitstatus = 1
        print(  # noqa: T201 - 收尾報告，必須讓 CI 的輸出看得到
            "\n⚠️ 測試行程密封被破壞：有測試把正式設定灌回環境變數\n"
            f"   洩漏的鍵（{len(leaked)}）：{'、'.join(leaked[:8])}"
            f"{' …' if len(leaked) > 8 else ''}\n"
            "   最常見的原因：某支測試呼叫了會 `load_dotenv()` 的進入點"
            "（`app.build_app`、`cron.worker.main`、`rag.worker.main`），\n"
            "   請在該測試以 monkeypatch 擋掉它——見 tests/test_app.py 的 `_build_app`。"
        )


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
    if url == _production_database_url():
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
