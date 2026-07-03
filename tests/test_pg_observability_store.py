import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def _store():
    from kinsun.db import Database, ensure_schema
    from kinsun.observability.store import PgTraceStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    tz = ZoneInfo("Asia/Taipei")
    return PgTraceStore(
        Database.open(url), clock=lambda: datetime.now(tz), new_id=lambda: uuid.uuid4().hex
    )


def test_record_and_get_trace_roundtrip():
    store = _store()
    trace_id = f"it-{uuid.uuid4().hex}"
    line_user_id = f"it-user-{os.getpid()}"
    store.record_webhook_event(
        trace_id=trace_id,
        line_user_id=line_user_id,
        event_type="message",
        message_type="audio",
        payload={"source": "it"},
    )
    store.record_asr_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=120,
        transcript="整合測試",
        source_audio_url="",
        error_message="",
    )
    store.record_llm_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=800,
        model_name="gemini-3.1-flash-lite",
        input_tokens=None,
        output_tokens=None,
        content="回覆",
        error_message="",
    )
    store.record_tts_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=300,
        content="回覆",
        error_message="",
    )
    store.record_reply(
        trace_id=trace_id,
        line_user_id=line_user_id,
        kind="voice",
        status="ok",
        latency_ms=100,
        audio_url="https://example.com/x.m4a",
    )
    trace = store.get_trace(trace_id)
    assert trace is not None
    assert trace.webhook_event.payload == {"source": "it"}
    assert trace.asr_call.transcript == "整合測試"
    assert len(trace.llm_calls) == 1
    assert trace.reply.kind == "voice"


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
