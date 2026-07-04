"""觀測層 Postgres Store 整合測試。

警語：本檔測試會實際寫入觀測五表（webhook_events／asr_calls／llm_calls／
tts_calls／replies），且 ``test_feed_overview_and_purge`` 會在結尾以未來
cutoff 呼叫 ``purge_older_than`` 清空這五張表——這將一併抹除同一資料庫中
他人的觀測資料。因此本檔僅限對「可拋棄的開發庫」執行，切勿對正式庫或共用
且不可清空的資料庫執行。需設定 ``KINSUN_IT=1`` 與 ``DATABASE_URL`` 才會啟用。
"""

import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def _store():
    from kinsun.db import Database, ensure_schema
    from kinsun.observability.store import PgTraceStore

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("需 DATABASE_URL 才能連開發庫")
    ensure_schema(url)
    tz = ZoneInfo("Asia/Taipei")
    return PgTraceStore(
        Database.open(url), clock=lambda: datetime.now(tz), new_id=lambda: uuid.uuid4().hex
    )


# 記錄面 record_* → get_trace 往返已移到跨 adapter 合約
# tests/test_observability_store_contract.py（pg 參數）；此處只保留查詢面
# （feed／overview）與 purge 整合測試，留待架構候選 #7 觀測層重構再處理。


def test_feed_overview_and_purge():
    store = _store()
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
    stats = store.get_overview_stats(today_start=0.0, hourly_start=0.0)
    assert any(s.stage == "asr" and s.call_count >= 1 for s in stats.stages)
    assert isinstance(store.list_feed(after=0.0, limit=5), list)
    assert isinstance(store.list_elders_with_last_active(), list)
    # 清掉本測試寫入的資料（cutoff 用未來時間即可全清觀測表）
    store.purge_older_than(datetime.now(ZoneInfo("Asia/Taipei")).timestamp() + 1)
    assert store.get_trace(trace_id) is None
