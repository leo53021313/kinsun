"""TraceStore 記錄面合約：Fake 與 Pg 兩個 adapter 對同一 record→get_trace
往返必須給出等價結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的 trace，才能在共用真庫上以「本輪鏈路」為單位斷言、互不干擾。

範圍：僅涵蓋記錄面（record_* → get_trace）往返。查詢面（feed／timeline／
overview）為跨表 UNION ALL 的原生 SQL，其等價性刻意延後到架構候選 #7
（觀測層重構）處理，不在本合約內；那些查詢面測試仍留在
``test_observability_store.py``（Fake）與 ``test_pg_observability_store.py``（Pg）。

斷言範圍說明：只斷言「兩邊都可靠產生」的欄位——即各 record_* 寫入的業務
內容（trace_id／external_id／payload／transcript／content／kind 等）。
刻意不斷言主鍵 *_id 與 created_at：主鍵由各自的 new_id／_next_id 產生、
created_at 由各自的 clock／now 決定，本非合約承諾的等價欄位。
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest

from kinsun.observability.store import FakeTraceStore, PgTraceStore

_FIXED_DT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        pg_db = request.getfixturevalue("pg_database")
        counter = itertools.count()
        return PgTraceStore(
            pg_db,
            clock=lambda: _FIXED_DT,
            new_id=lambda: f"{ns}id{next(counter)}",
        )
    return FakeTraceStore()


def _record_full_trace(store, *, trace_id: str, external_id: str, channel: str = "line") -> None:
    store.record_webhook_event(
        trace_id=trace_id,
        external_id=external_id,
        channel=channel,
        event_type="message",
        message_type="audio",
        payload={"k": "v"},
    )
    store.record_asr_call(
        trace_id=trace_id,
        external_id=external_id,
        channel=channel,
        status="ok",
        latency_ms=120,
        transcript="阿公早安",
        source_audio_url="https://x/in.m4a",
        error_message="",
    )
    store.record_llm_call(
        trace_id=trace_id,
        external_id=external_id,
        channel=channel,
        status="ok",
        latency_ms=800,
        model_name="gemini-3.1-flash-lite",
        input_tokens=512,
        output_tokens=64,
        content="早安，睡得好嗎？",
        error_message="",
    )
    store.record_tts_call(
        trace_id=trace_id,
        external_id=external_id,
        channel=channel,
        status="ok",
        latency_ms=300,
        content="早安，睡得好嗎？",
        error_message="",
    )
    store.record_reply(
        trace_id=trace_id,
        external_id=external_id,
        channel=channel,
        kind="voice",
        status="ok",
        latency_ms=150,
        round_trip_ms=950,
        audio_url="https://x/out.m4a",
    )


def test_record_then_get_trace_roundtrip(store, ns):
    trace_id = f"{ns}trace"
    external_id = f"{ns}user"
    _record_full_trace(store, trace_id=trace_id, external_id=external_id)

    trace = store.get_trace(trace_id)
    assert trace is not None
    assert trace.trace_id == trace_id
    assert trace.external_id == external_id
    # ✅ 庚-07（A-8）：channel 隨 external_id 一併留痕、round-trip 取回。
    assert trace.channel == "line"

    assert trace.webhook_event is not None
    assert trace.webhook_event.channel == "line"
    assert trace.webhook_event.event_type == "message"
    assert trace.webhook_event.message_type == "audio"
    assert trace.webhook_event.payload == {"k": "v"}

    assert trace.asr_call is not None
    assert trace.asr_call.status == "ok"
    assert trace.asr_call.latency_ms == 120
    assert trace.asr_call.transcript == "阿公早安"
    assert trace.asr_call.source_audio_url == "https://x/in.m4a"

    assert [c.content for c in trace.llm_calls] == ["早安，睡得好嗎？"]
    assert trace.llm_calls[0].model_name == "gemini-3.1-flash-lite"
    assert trace.llm_calls[0].input_tokens == 512
    assert trace.llm_calls[0].output_tokens == 64

    assert trace.tts_call is not None
    assert trace.tts_call.content == "早安，睡得好嗎？"
    assert trace.tts_call.latency_ms == 300

    assert trace.reply is not None
    assert trace.reply.kind == "voice"
    assert trace.reply.audio_url == "https://x/out.m4a"
    # 往返延遲（✅ D-05 戊-2）：端到端 round_trip_ms 與發送段 latency_ms 各自留存。
    assert trace.reply.latency_ms == 150
    assert trace.reply.round_trip_ms == 950

    # 未記錄任何風險事件，兩邊都應回空清單（記錄面不寫 risk_events）。
    assert trace.risk_events == []


def test_get_trace_missing_returns_none(store, ns):
    assert store.get_trace(f"{ns}nope") is None


def test_get_trace_with_only_reply_still_bundles(store, ns):
    # 部分鏈路：只落一筆 reply，get_trace 仍應回一個含該 reply 的 Trace，
    # 其餘子紀錄為 None／空清單。
    trace_id = f"{ns}partial"
    external_id = f"{ns}user"
    store.record_reply(
        trace_id=trace_id,
        external_id=external_id,
        kind="text",
        status="ok",
        latency_ms=10,
        round_trip_ms=None,
        audio_url="",
    )
    trace = store.get_trace(trace_id)
    assert trace is not None
    assert trace.external_id == external_id
    assert trace.webhook_event is None
    assert trace.asr_call is None
    assert trace.llm_calls == []
    assert trace.tts_call is None
    assert trace.reply is not None
    assert trace.reply.kind == "text"
