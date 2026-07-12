"""觀測層 Postgres Store 整合測試。

警語：本檔測試會實際寫入觀測五表（webhook_events／asr_calls／llm_calls／
tts_calls／replies），且 ``test_feed_overview_and_purge`` 會在結尾以未來
cutoff 呼叫 ``purge_older_than`` 清空這五張表——這將一併抹除同一資料庫中
他人的觀測資料。因此本檔僅限對「可拋棄的開發庫」執行，切勿對正式庫或共用
且不可清空的資料庫執行。需 ``KINSUN_IT=1``＋``KINSUN_TEST_DATABASE_URL``
（獨立測試庫，✅ D-69 禁連正式庫）才會啟用。
"""

import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("KINSUN_IT") != "1", reason="需 KINSUN_IT=1（連獨立測試庫）"
)


def _store(pg_database):
    from kinsun.observability.store import PgTraceStore

    tz = ZoneInfo("Asia/Taipei")
    return PgTraceStore(
        pg_database, clock=lambda: datetime.now(tz), new_id=lambda: uuid.uuid4().hex
    )


# 記錄面 record_* → get_trace 往返已移到跨 adapter 合約
# tests/test_observability_store_contract.py（pg 參數）；此處只保留查詢面
# （feed／overview）與 purge 整合測試，留待架構候選 #7 觀測層重構再處理。


def test_feed_overview_and_purge(pg_database):
    store = _store(pg_database)
    trace_id = f"it-{uuid.uuid4().hex}"
    line_user_id = f"it-user-{uuid.uuid4().hex[:8]}"
    store.record_asr_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=50,
        transcript="嗨",
        source_audio_url="",
        error_message="",
    )
    # 往返延遲統計（✅ D-05 戊-2）：percentile_cont 的 p50／p95 在真 Postgres 上驗語法與插值。
    for round_trip_ms in (700, 900, 1400):
        store.record_reply(
            trace_id=trace_id,
            line_user_id=line_user_id,
            kind="voice",
            status="ok",
            latency_ms=100,
            round_trip_ms=round_trip_ms,
            audio_url="",
        )
    store.record_reply(
        trace_id=trace_id,
        line_user_id=line_user_id,
        kind="text",
        status="ok",
        latency_ms=5,
        round_trip_ms=None,
        audio_url="",
    )
    stats = store.get_overview_stats(today_start=0.0, hourly_start=0.0)
    assert any(s.stage == "asr" and s.call_count >= 1 for s in stats.stages)
    # 只看最近 60 秒視窗，隔離同庫其他測試（如合約測試）寫入的 replies。
    recent_ts = datetime.now(ZoneInfo("Asia/Taipei")).timestamp() - 60
    recent = store.get_overview_stats(today_start=recent_ts, hourly_start=recent_ts)
    round_trip = next(s for s in recent.stages if s.stage == "round_trip")
    assert round_trip.call_count == 3  # round_trip_ms 為 NULL（未量測）者不計
    assert round_trip.p50_latency_ms == 900.0
    assert round_trip.p95_latency_ms == 1350.0  # percentile_cont 線性插值：900＋0.9×500
    # 活躍長輩數以 elder_id 計（✅ D-34 丙-4）：line_user_id 已退役恆 NULL，舊查詢在真庫恆 0。
    now_ts = datetime.now(ZoneInfo("Asia/Taipei")).timestamp()
    before = store.get_overview_stats(today_start=now_ts - 60, hourly_start=now_ts - 60)
    pg_database.execute(
        "INSERT INTO turns (elder_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
        ("e-active-1", "user", "早安", now_ts),
    )
    pg_database.execute(
        "INSERT INTO turns (elder_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
        ("e-active-2", "user", "午安", now_ts),
    )
    after = store.get_overview_stats(today_start=now_ts - 60, hourly_start=now_ts - 60)
    assert after.active_elder_count - before.active_elder_count == 2
    pg_database.execute("DELETE FROM turns WHERE elder_id IN ('e-active-1', 'e-active-2')", ())
    assert isinstance(store.list_feed(after=0.0, limit=5), list)
    # before 游標（✅ D-29 乙-6）：動態 WHERE 條件需在真 Postgres 上驗語法。
    assert isinstance(store.list_feed(after=0.0, before=9e12, limit=5), list)
    assert isinstance(store.list_elders_with_last_active(), list)
    # 清掉本測試寫入的資料（cutoff 用未來時間即可全清觀測表）
    store.purge_older_than(datetime.now(ZoneInfo("Asia/Taipei")).timestamp() + 1)
    assert store.get_trace(trace_id) is None
