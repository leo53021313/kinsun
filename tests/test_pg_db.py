"""ensure_schema 的併發遷移防護（諮詢鎖）整合測試。

需連真實 Postgres：設定 ``KINSUN_IT=1`` 與 ``DATABASE_URL`` 才會啟用。
驗證 webhook 與 scheduler 同時啟動時，兩者的 ensure_schema 不會併發跑 DDL
互搶 AccessExclusiveLock 而死結——改以交易級諮詢鎖串行化。
"""

import os
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def _advisory_waiters(conn, key: int) -> int:
    """回傳目前卡在等待這把諮詢鎖（key 為單參數 bigint 形式）的連線數。
    單參數形式在 pg_locks 為 classid=key>>32、objid=key、objsubid=1。"""
    row = conn.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND classid = 0 AND objid::bigint = %s AND objsubid = 1 AND NOT granted",
        (key,),
    ).fetchone()
    return int(row[0])


def test_ensure_schema_serialized_by_advisory_lock():
    from kinsun.db import SCHEMA_MIGRATION_LOCK_KEY, connect, ensure_schema

    url = os.environ["DATABASE_URL"]
    # 先讓 schema 就緒（排除首次建表雜訊），並確認單獨呼叫本身可正常完成。
    ensure_schema(url)

    # 在另一條 session 持有同一把遷移鎖，模擬「已有一個行程正在遷移」。
    holder = connect(url)
    holder.autocommit = True
    holder.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_MIGRATION_LOCK_KEY,))
    done = threading.Event()

    def run() -> None:
        ensure_schema(url)
        done.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        # 鎖被他人持有時，被修好的 ensure_schema 應「開頭就搶同一把諮詢鎖並卡住」，
        # 於是 pg_locks 會出現一筆未授予（NOT granted）的等待者。未修的版本永遠不會出現。
        deadline = time.monotonic() + 5.0
        waiting = 0
        while time.monotonic() < deadline:
            waiting = _advisory_waiters(holder, SCHEMA_MIGRATION_LOCK_KEY)
            if waiting >= 1:
                break
            time.sleep(0.1)
        assert waiting >= 1, "ensure_schema 未在遷移前搶諮詢鎖，仍有併發遷移死結風險"
        # 既然卡在搶鎖，就不應該已完成。
        assert not done.is_set(), "ensure_schema 未被諮詢鎖擋住即完成"
    finally:
        holder.execute("SELECT pg_advisory_unlock(%s)", (SCHEMA_MIGRATION_LOCK_KEY,))
    # 放鎖後應能順利完成。
    assert done.wait(timeout=15.0), "放鎖後 ensure_schema 仍未完成"
    worker.join(timeout=1.0)
    holder.close()


def test_ensure_schema_concurrent_no_deadlock():
    """重現原始情境：多個行程（webhook、scheduler…）同時啟動一起跑 ensure_schema。
    有了諮詢鎖串行化，全部都應成功、無人因 DeadlockDetected 崩潰。"""
    from kinsun.db import ensure_schema

    url = os.environ["DATABASE_URL"]
    n = 10
    start = threading.Barrier(n)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def run() -> None:
        start.wait()  # 讓所有執行緒盡量同一瞬間開跑，逼出併發遷移
        try:
            ensure_schema(url)
        except BaseException as exc:  # noqa: BLE001 - 測試需捕捉任何遷移失敗
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)

    names = [type(e).__name__ for e in errors]
    assert not errors, f"併發 ensure_schema 出現錯誤（含死結）：{names}"


def test_channel_bindings_backfill_idempotent(pg_database, ns):
    from kinsun.db import ensure_schema

    # 模擬「雙寫上線前」的舊資料：直接寫欄位、清掉綁定列。
    pg_database.execute(
        "INSERT INTO elders (elder_id, name, line_user_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (elder_id) DO UPDATE SET line_user_id = EXCLUDED.line_user_id",
        (f"{ns}e-bf", "阿公", f"{ns}U-bf"),
    )
    pg_database.execute(
        "DELETE FROM channel_bindings WHERE channel = 'line' AND external_id = %s",
        (f"{ns}U-bf",),
    )
    ensure_schema(os.environ["DATABASE_URL"])
    ensure_schema(os.environ["DATABASE_URL"])  # 冪等：跑兩次結果不變
    rows = pg_database.query(
        "SELECT principal_type, principal_id FROM channel_bindings "
        "WHERE channel = 'line' AND external_id = %s",
        (f"{ns}U-bf",),
    )
    assert rows == [("elder", f"{ns}e-bf")]


def test_session_key_migration_columns_and_backfill(pg_database, ns):
    from kinsun.db import ensure_schema

    # 造一筆「可對應長輩」的舊制對話（直接寫 line_user_id 欄），與一位已綁定長輩。
    pg_database.execute(
        "INSERT INTO elders (elder_id, name, line_user_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (elder_id) DO UPDATE SET line_user_id = EXCLUDED.line_user_id",
        (f"{ns}e-mig", "阿公", f"{ns}U-mig"),
    )
    pg_database.execute(
        "INSERT INTO turns (line_user_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
        (f"{ns}U-mig", "user", "舊制訊息", 1000.0),
    )
    ensure_schema(os.environ["DATABASE_URL"])
    ensure_schema(os.environ["DATABASE_URL"])  # 冪等
    rows = pg_database.query(
        "SELECT elder_id FROM turns WHERE line_user_id = %s", (f"{ns}U-mig",)
    )
    assert rows == [(f"{ns}e-mig",)]
    # 新制寫入：不帶 line_user_id 也能落列（欄位已可空）。
    pg_database.execute(
        "INSERT INTO turns (elder_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
        (f"{ns}e-mig", "user", "新制訊息", 2000.0),
    )
    # 摘要：新制以 (elder_id, date) upsert（部分唯一索引生效）。
    for content in ("v1", "v2"):
        pg_database.execute(
            "INSERT INTO conversation_summaries (elder_id, date, content, created_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (elder_id, date) WHERE elder_id IS NOT NULL "
            "DO UPDATE SET content = EXCLUDED.content, created_at = EXCLUDED.created_at",
            (f"{ns}e-mig", "2026-07-07", content, 3000.0),
        )
    rows = pg_database.query(
        "SELECT content FROM conversation_summaries WHERE elder_id = %s AND date = %s",
        (f"{ns}e-mig", "2026-07-07"),
    )
    assert rows == [("v2",)]
