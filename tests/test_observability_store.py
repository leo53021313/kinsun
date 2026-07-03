from tests.fakes import FakeTraceStore


def _record_full_trace(store, trace_id="t1", line_user_id="U1"):
    store.record_webhook_event(
        trace_id=trace_id,
        line_user_id=line_user_id,
        event_type="message",
        message_type="audio",
        payload={"k": "v"},
    )
    store.record_asr_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=120,
        transcript="阿公早安",
        source_audio_url="https://x/in.m4a",
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
        content="早安，睡得好嗎？",
        error_message="",
    )
    store.record_tts_call(
        trace_id=trace_id,
        line_user_id=line_user_id,
        status="ok",
        latency_ms=300,
        content="早安，睡得好嗎？",
        error_message="",
    )
    store.record_reply(
        trace_id=trace_id,
        line_user_id=line_user_id,
        kind="voice",
        status="ok",
        latency_ms=150,
        audio_url="https://x/out.m4a",
    )


def test_get_trace_bundles_all_stages():
    store = FakeTraceStore()
    _record_full_trace(store)
    trace = store.get_trace("t1")
    assert trace is not None
    assert trace.line_user_id == "U1"
    assert trace.webhook_event.payload == {"k": "v"}
    assert trace.asr_call.transcript == "阿公早安"
    assert [c.content for c in trace.llm_calls] == ["早安，睡得好嗎？"]
    assert trace.tts_call.latency_ms == 300
    assert trace.reply.audio_url == "https://x/out.m4a"
    assert trace.risk_events == []


def test_get_trace_missing_returns_none():
    assert FakeTraceStore().get_trace("nope") is None


def test_get_trace_includes_seeded_risk_events():
    store = FakeTraceStore()
    _record_full_trace(store, trace_id="t2")
    store.seed_risk("U1", 3, "跌倒", 5.0, trace_id="t2")
    trace = store.get_trace("t2")
    assert [(r.tier, r.reason) for r in trace.risk_events] == [(3, "跌倒")]


def test_created_at_follows_fake_clock():
    store = FakeTraceStore()
    store.now = 42.0
    store.record_reply(
        trace_id="t3",
        line_user_id="U1",
        kind="text",
        status="ok",
        latency_ms=1,
        audio_url="",
    )
    assert store.replies[0].created_at == 42.0


def test_safe_record_swallows_exceptions():
    from kinsun.observability.store import safe_record

    def boom() -> None:
        raise RuntimeError("db down")

    safe_record(boom)  # 不應丟出例外
