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


def test_list_feed_merges_sources_desc_and_respects_after_limit():
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公", "U1")
    store.seed_turn("U1", "user", "早安", 10.0)
    store.seed_turn("U1", "assistant", "阿公早", 20.0)
    store.seed_reminder("e1", "medication", "早上用藥提醒", 30.0)
    store.seed_risk("U1", 2, "頭暈", 40.0, trace_id="t9")
    feed = store.list_feed(after=15.0, limit=2)
    assert [(i.kind, i.created_at) for i in feed] == [("risk", 40.0), ("reminder", 30.0)]
    assert feed[0].trace_id == "t9"
    assert feed[0].elder_name == "阿公"
    assert feed[1].line_user_id == "U1"  # reminder 由 elder_id 反查


def test_list_timeline_includes_voice_cards_in_time_order():
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公", "U1")
    store.now = 10.0
    store.record_asr_call(
        trace_id="t1",
        line_user_id="U1",
        status="ok",
        latency_ms=1,
        transcript="早安",
        source_audio_url="https://x/in.m4a",
        error_message="",
    )
    store.seed_turn("U1", "user", "早安", 11.0)
    store.seed_turn("U1", "assistant", "阿公早", 12.0)
    store.now = 13.0
    store.record_reply(
        trace_id="t1",
        line_user_id="U1",
        kind="voice",
        status="ok",
        latency_ms=1,
        audio_url="https://x/out.m4a",
    )
    store.seed_risk("U2", 3, "別人的事件", 12.5)  # 不同長輩，不應出現
    items = store.list_timeline_for_elder(elder_id="e1", line_user_id="U1", start=0.0, end=100.0)
    assert [i.kind for i in items] == ["voice", "turn", "turn", "voice"]
    assert items[0].trace_id == "t1" and items[0].audio_url == "https://x/in.m4a"
    assert items[3].role == "assistant" and items[3].audio_url == "https://x/out.m4a"


def test_list_elders_with_last_active():
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公", "U1")
    store.seed_elder("e2", "阿嬤", "")
    store.seed_turn("U1", "user", "hi", 5.0)
    store.seed_turn("U1", "user", "hi2", 9.0)
    elders = store.list_elders_with_last_active()
    by_id = {e.elder_id: e for e in elders}
    assert by_id["e1"].last_active_at == 9.0
    assert by_id["e2"].last_active_at is None
