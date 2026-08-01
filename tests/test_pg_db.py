"""ensure_schema 的遷移整合測試（併發防護、既有庫升級）。

需連獨立測試庫：設定 ``KINSUN_IT=1`` 與 ``KINSUN_TEST_DATABASE_URL`` 才會啟用
（✅ D-69：不再直連 DATABASE_URL 正式庫）。
驗證 webhook 與 scheduler 同時啟動時，兩者的 ensure_schema 不會併發跑 DDL
互搶 AccessExclusiveLock 而死結——改以交易級諮詢鎖串行化。
另驗證帶著舊資料的既有庫（庚-07 之前的 line_user_id 觀測表）能就地升級——
空庫路徑（CREATE TABLE 直接建新欄）測不到這條，得先造出舊 schema 才會踩到。
"""

import os
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("KINSUN_IT") != "1", reason="需 KINSUN_IT=1（連獨立測試庫）"
)


def _advisory_waiters(conn, key: int) -> int:
    """回傳目前卡在等待這把諮詢鎖（key 為單參數 bigint 形式）的連線數。
    單參數形式在 pg_locks 為 classid=key>>32、objid=key、objsubid=1。"""
    row = conn.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND classid = 0 AND objid::bigint = %s AND objsubid = 1 AND NOT granted",
        (key,),
    ).fetchone()
    return int(row[0])


def test_ensure_schema_serialized_by_advisory_lock(pg_url):
    from kinsun.db import SCHEMA_MIGRATION_LOCK_KEY, connect, ensure_schema

    url = pg_url
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


def test_ensure_schema_concurrent_no_deadlock(pg_url):
    """重現原始情境：多個行程（webhook、scheduler…）同時啟動一起跑 ensure_schema。
    有了諮詢鎖串行化，全部都應成功、無人因 DeadlockDetected 崩潰。"""
    from kinsun.db import ensure_schema

    url = pg_url
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


def test_session_key_schema_supports_elder_keys(pg_database, pg_url, ns):
    from kinsun.db import ensure_schema

    ensure_schema(pg_url)
    ensure_schema(pg_url)  # 冪等（含帳號欄位退役 DDL）
    # 帳號欄位已退役：elders 不再有 line_user_id。
    cols = pg_database.query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'elders' AND column_name = 'line_user_id'",
    )
    assert cols == []
    # 新制寫入：turns 以 elder_id 為鍵、不帶 line_user_id 也能落列。
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


_LEGACY_APPOINTMENTS_DDL = (
    "CREATE TABLE appointments ("
    "appointment_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, "
    "date TEXT NOT NULL, label TEXT NOT NULL, time TEXT NOT NULL DEFAULT '');"
)


def test_ensure_schema_retires_the_legacy_reminder_tables(pg_url):
    """D-76 P5：舊的用藥與回診表必須被丟掉。

    留著不管會讓下一個人以為那還是真相來源，而它的內容自 P3 家屬入口切換後就再也
    不會更新了——一份看起來像資料、實際上已經停止呼吸的表，比沒有更危險。
    """
    from kinsun.db import connect, ensure_schema

    with connect(pg_url) as conn:
        conn.execute("DROP TABLE IF EXISTS appointments CASCADE;")
        conn.execute(_LEGACY_APPOINTMENTS_DDL)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS medications ("
            "medication_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, "
            "name TEXT NOT NULL, slots TEXT NOT NULL);"
        )
        conn.commit()

    ensure_schema(pg_url)

    with connect(pg_url) as conn:
        remaining = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename IN ('medications', 'appointments')"
        ).fetchall()
        assert remaining == []
        # 新表必須還在——退役步驟排在建表之後，不可把兩者的順序調換。
        assert _columns_of(conn, "schedules")


# 庚-07 正名前的觀測五表 schema（取自 commit e7ec9d0）：欄位還叫 line_user_id、
# 沒有 channel。正式庫就是長這樣，用來重現「既有庫升級」路徑。
_LEGACY_OBSERVABILITY_DDL = (
    "CREATE TABLE webhook_events ("
    "webhook_event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, "
    "line_user_id TEXT NOT NULL, event_type TEXT NOT NULL, message_type TEXT NOT NULL, "
    "payload JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE asr_calls ("
    "asr_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, line_user_id TEXT NOT NULL, "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, transcript TEXT NOT NULL, "
    "source_audio_url TEXT NOT NULL, error_message TEXT NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX idx_asr_calls_line_user_created ON asr_calls (line_user_id, created_at);"
    "CREATE TABLE llm_calls ("
    "llm_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, line_user_id TEXT NOT NULL, "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, model_name TEXT NOT NULL, "
    "input_tokens INTEGER, output_tokens INTEGER, content TEXT NOT NULL, "
    "error_message TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE tts_calls ("
    "tts_call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, line_user_id TEXT NOT NULL, "
    "status TEXT NOT NULL, latency_ms INTEGER NOT NULL, content TEXT NOT NULL, "
    "error_message TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE TABLE replies ("
    "reply_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, line_user_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, status TEXT NOT NULL, latency_ms INTEGER NOT NULL, "
    "round_trip_ms INTEGER, audio_url TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)

_OBSERVABILITY_TABLE_NAMES = ("webhook_events", "asr_calls", "llm_calls", "tts_calls", "replies")


def _columns_of(conn, table: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    ).fetchall()
    return {row[0] for row in rows}


def test_ensure_schema_upgrades_legacy_line_user_id_observability_tables(pg_url):
    """既有庫升級（✅ 庚-07 正名）：觀測五表原本是 line_user_id，ensure_schema 須能就地
    改名為 external_id、補上 channel，且不得掉資料。

    空庫路徑測不到這條——CREATE TABLE 一開始就建 external_id，改名遷移自動略過。
    只有帶著舊表的既有庫會走到「建索引時 external_id 還不存在」。
    """
    from kinsun.db import connect, ensure_schema

    # 造出庚-07 之前的既有庫：五表帶 line_user_id、無 external_id／channel，且有既存資料。
    with connect(pg_url) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {', '.join(_OBSERVABILITY_TABLE_NAMES)} CASCADE;")
        conn.execute(_LEGACY_OBSERVABILITY_DDL)
        conn.execute(
            "INSERT INTO asr_calls (asr_call_id, trace_id, line_user_id, status, latency_ms, "
            "transcript, source_audio_url, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("legacy-asr-1", "trace-1", "U-legacy", "ok", 120, "早安", "", "", 1000.0),
        )
        conn.commit()

    # 舊庫升級不得拋 UndefinedColumn（線上 webhook／scheduler 就是死在這裡）。
    ensure_schema(pg_url)

    with connect(pg_url) as conn:
        for table in _OBSERVABILITY_TABLE_NAMES:
            cols = _columns_of(conn, table)
            assert "external_id" in cols, f"{table} 未改名出 external_id"
            assert "channel" in cols, f"{table} 未補上 channel"
            assert "line_user_id" not in cols, f"{table} 仍留著舊欄 line_user_id"
        # 改名須保住原資料（不得以 DROP＋ADD 重建欄位）。
        row = conn.execute(
            "SELECT external_id, channel, transcript FROM asr_calls WHERE asr_call_id = %s",
            ("legacy-asr-1",),
        ).fetchone()
        assert row == ("U-legacy", "", "早安")
        # 改名殘骸須清掉：舊索引改名後與 idx_asr_calls_external_created 定義相同，
        # 兩份同內容的 btree 只是白白拖慢寫入。
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'asr_calls'"
            ).fetchall()
        }
        assert "idx_asr_calls_line_user_created" not in indexes, "舊索引未清除（與新索引重複）"
        assert "idx_asr_calls_external_created" in indexes

    ensure_schema(pg_url)  # 冪等：升級後再跑一次仍須成功


def test_ensure_schema_adds_llm_call_kind_to_legacy_table(pg_url):
    """既有庫升級（2026-07-25 濫用審核）：llm_calls 須就地補上 kind 欄。

    空庫路徑一樣測不到——新庫的 ALTER 緊接在 CREATE TABLE 之後、必定成功。只有帶著
    舊表與舊資料的既有庫，才驗得到「補欄不炸、舊列拿到預設值、既存資料不掉」。
    舊列的 kind 必須是空字串（＝未標記），不可被塞進任何一個真實種類——否則後台的
    逐種類統計會把加欄前的資料算進去，數字失真。
    """
    from kinsun.db import connect, ensure_schema

    with connect(pg_url) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {', '.join(_OBSERVABILITY_TABLE_NAMES)} CASCADE;")
        conn.execute(_LEGACY_OBSERVABILITY_DDL)  # 這份舊 schema 的 llm_calls 沒有 kind
        conn.execute(
            "INSERT INTO llm_calls (llm_call_id, trace_id, line_user_id, status, latency_ms, "
            "model_name, input_tokens, output_tokens, content, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("legacy-llm-1", "trace-1", "U-legacy", "ok", 800, "gemini", 10, 20, "嗨", "", 1000.0),
        )
        conn.commit()

    ensure_schema(pg_url)

    with connect(pg_url) as conn:
        assert "kind" in _columns_of(conn, "llm_calls"), "llm_calls 未補上 kind"
        row = conn.execute(
            "SELECT kind, content, input_tokens FROM llm_calls WHERE llm_call_id = %s",
            ("legacy-llm-1",),
        ).fetchone()
        assert row == ("", "嗨", 10), "舊列的 kind 應為空字串且原資料不得遺失"

    ensure_schema(pg_url)  # 冪等


def test_transaction_lets_domain_exceptions_pass_through(pg_database, ns):
    """✅ 庚-19 修訂：交易本體拋出的業務例外須原樣穿透（不得被誤包成 StoreError）——
    否則 redeem 在交易內拋的 InviteError 會被 _Errors 再翻成 AccountError，
    呼叫端接不到正確錯誤型別。回滾仍須發生。"""

    class _DomainError(Exception):
        pass

    pg_database.execute(
        "INSERT INTO scheduler_state (job_name, last_run_at) VALUES (%s, %s) "
        "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at",
        (f"{ns}tx-job", 1000.0),
    )
    with pytest.raises(_DomainError):
        with pg_database.transaction() as tx:
            tx.execute(
                "UPDATE scheduler_state SET last_run_at = %s WHERE job_name = %s",
                (2000.0, f"{ns}tx-job"),
            )
            raise _DomainError("業務錯誤")
    row = pg_database.query_one(
        "SELECT last_run_at FROM scheduler_state WHERE job_name = %s", (f"{ns}tx-job",)
    )
    assert row == (1000.0,)  # 已回滾


# PR #55 的 elder_locations schema：只有地名、沒有座標。正式庫就是長這樣。
_LEGACY_ELDER_LOCATIONS_DDL = (
    "CREATE TABLE elder_locations ("
    "elder_id TEXT PRIMARY KEY, place TEXT NOT NULL, "
    "recorded_at DOUBLE PRECISION NOT NULL);"
)


def test_ensure_schema_adds_coords_to_legacy_elder_locations(pg_url):
    """既有庫升級：elder_locations 已於 PR #55 上線、沒有座標欄位，
    ensure_schema 須能就地補上，且不得掉既有資料。

    空庫路徑測不到這條——CREATE TABLE 一開始就會建出座標欄，ALTER 自動略過。
    只有帶著舊表的既有庫（正式庫就是）會走到 ALTER 那條路。
    """
    from kinsun.db import connect, ensure_schema

    with connect(pg_url) as conn:
        conn.execute("DROP TABLE IF EXISTS elder_locations CASCADE;")
        conn.execute(_LEGACY_ELDER_LOCATIONS_DDL)
        conn.execute(
            "INSERT INTO elder_locations (elder_id, place, recorded_at) VALUES (%s, %s, %s)",
            ("legacy-e1", "台南市", 1000.0),
        )
        conn.commit()

    ensure_schema(pg_url)

    with connect(pg_url) as conn:
        cols = _columns_of(conn, "elder_locations")
        assert "latitude" in cols, "未補上 latitude"
        assert "longitude" in cols, "未補上 longitude"
        row = conn.execute(
            "SELECT place, recorded_at, latitude, longitude FROM elder_locations "
            "WHERE elder_id = %s",
            ("legacy-e1",),
        ).fetchone()
        # 既有列必須留著，且座標為 NULL——語意正確（我們確實不知道它在哪）。
        assert row == ("台南市", 1000.0, None, None)


# app_notifications 加 severity 之前的 schema（取自 commit 9702796）：只有四個欄位，
# 沒有任何欄位分得出「危急警報」與「用藥提醒」。正式庫自 D-12 上線至今就是長這樣。
_LEGACY_APP_NOTIFICATIONS_DDL = (
    "CREATE TABLE app_notifications ("
    "app_notification_id TEXT PRIMARY KEY, external_id TEXT NOT NULL, "
    "content TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
)


def test_ensure_schema_adds_severity_to_legacy_app_notifications(pg_url):
    """既有庫升級（2026-08-01 通知分級）：app_notifications 須就地補上 severity。

    空庫路徑測不到這條——新庫的 CREATE TABLE 一開始就帶 severity，ALTER 自動略過。
    只有帶著舊表與舊資料的既有庫（正式庫就是）才會走到 ALTER 那條路；漏了它，
    線上第一次寫通知就炸 UndefinedColumn，而所有的離線測試都會是綠的。

    舊列一律是 `notice`：寫入當時沒留下任何分類線索，無從回溯分辨哪幾則其實是
    危急警報。這是**刻意接受的失真**（見 db.py 該段說明）——猜錯的方向與現況相同，
    而全部標成 alert 會讓每一則舊的用藥提醒都變成紅色警報。
    """
    from kinsun.db import connect, ensure_schema

    with connect(pg_url) as conn:
        conn.execute("DROP TABLE IF EXISTS app_notifications CASCADE;")
        conn.execute(_LEGACY_APP_NOTIFICATIONS_DDL)
        conn.execute(
            "INSERT INTO app_notifications "
            "(app_notification_id, external_id, content, created_at) VALUES (%s, %s, %s, %s)",
            ("legacy-n1", "dev-legacy", "⚠️【金孫關懷提醒】您關心的長輩剛剛說：…", 1000.0),
        )
        conn.commit()

    # 舊庫升級不得拋 UndefinedColumn。
    ensure_schema(pg_url)

    with connect(pg_url) as conn:
        assert "severity" in _columns_of(conn, "app_notifications"), "未補上 severity"
        row = conn.execute(
            "SELECT content, created_at, severity FROM app_notifications "
            "WHERE app_notification_id = %s",
            ("legacy-n1",),
        ).fetchone()
        # 既有列必須留著（不得以重建表的方式加欄），且一律降級為一般通知。
        assert row == ("⚠️【金孫關懷提醒】您關心的長輩剛剛說：…", 1000.0, "notice")

    ensure_schema(pg_url)  # 冪等：升級後再跑一次仍須成功


def test_legacy_app_notifications_upgrade_then_accepts_alert_writes(pg_url):
    """升級後的既有庫必須真的寫得進 alert——只驗「欄位長出來了」還不夠。

    ⚠️ 這條與上一條刻意分開：上一條驗的是 DDL，這條驗的是**升級後的表接得住
    正式寫入路徑**（PgAppNotificationStore.record）。「欄位在」與「寫得進去」是
    兩件事——NOT NULL＋DEFAULT 若沒設對，前者會過、後者會炸。
    """
    from datetime import datetime, timedelta, timezone

    from kinsun.db import Database, connect, ensure_schema
    from kinsun.notifications.models import NotificationSeverity
    from kinsun.notifications.store import PgAppNotificationStore

    with connect(pg_url) as conn:
        conn.execute("DROP TABLE IF EXISTS app_notifications CASCADE;")
        conn.execute(_LEGACY_APP_NOTIFICATIONS_DDL)
        conn.execute(
            "INSERT INTO app_notifications "
            "(app_notification_id, external_id, content, created_at) VALUES (%s, %s, %s, %s)",
            ("legacy-n2", "dev-legacy2", "早安，記得吃藥", 1000.0),
        )
        conn.commit()

    ensure_schema(pg_url)

    clock = datetime(2026, 8, 1, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    database = Database.open(pg_url)
    try:
        store = PgAppNotificationStore(database, clock=lambda: clock, new_id=lambda: "upgraded-n1")
        store.record("dev-legacy2", "跌倒了", severity=NotificationSeverity.ALERT)
        got = store.list_for_external_ids(["dev-legacy2"])
    finally:
        database.close()

    # 新寫入的是 alert，升級前就存在的那列仍是 notice——兩者在同一張表上並存。
    assert [(n.content, n.severity) for n in got] == [
        ("跌倒了", NotificationSeverity.ALERT),
        ("早安，記得吃藥", NotificationSeverity.NOTICE),
    ]
