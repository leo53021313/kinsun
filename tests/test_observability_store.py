from tests.fakes import FakeTraceStore


def _record_full_trace(store, trace_id="t1", external_id="U1"):
    store.record_webhook_event(
        trace_id=trace_id,
        external_id=external_id,
        event_type="message",
        message_type="audio",
        payload={"k": "v"},
    )
    store.record_asr_call(
        trace_id=trace_id,
        external_id=external_id,
        status="ok",
        latency_ms=120,
        transcript="阿公早安",
        source_audio_url="https://x/in.m4a",
        error_message="",
    )
    store.record_llm_call(
        trace_id=trace_id,
        external_id=external_id,
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
        external_id=external_id,
        status="ok",
        latency_ms=300,
        content="早安，睡得好嗎？",
        error_message="",
    )
    store.record_reply(
        trace_id=trace_id,
        external_id=external_id,
        kind="voice",
        status="ok",
        latency_ms=150,
        audio_url="https://x/out.m4a",
    )


# 記錄面 record_* → get_trace 往返（含 missing 回 None）已移到跨 adapter 合約
# tests/test_observability_store_contract.py；此處只保留 Fake 專屬與查詢面測試。


def test_get_trace_includes_seeded_risk_events():
    store = FakeTraceStore()
    _record_full_trace(store, trace_id="t2")
    store.seed_risk("e1", 3, "跌倒", 5.0, trace_id="t2")
    trace = store.get_trace("t2")
    assert [(r.tier, r.reason) for r in trace.risk_events] == [(3, "跌倒")]


def test_created_at_follows_fake_clock():
    store = FakeTraceStore()
    store.now = 42.0
    store.record_reply(
        trace_id="t3",
        external_id="U1",
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
    store.seed_elder("e1", "阿公")
    store.seed_turn("e1", "user", "早安", 10.0)
    store.seed_turn("e1", "assistant", "阿公早", 20.0)
    store.seed_reminder("e1", "medication", "早上用藥提醒", 30.0)
    store.seed_risk("e1", 2, "頭暈", 40.0, trace_id="t9")
    feed = store.list_feed(after=15.0, limit=2)
    assert [(i.kind, i.created_at) for i in feed] == [("risk", 40.0), ("reminder", 30.0)]
    assert feed[0].trace_id == "t9"
    assert feed[0].elder_name == "阿公"
    assert feed[1].elder_id == "e1"


def test_list_feed_before_cursor_pages_history():
    """✅ D-29（乙-6）：before 游標回翻歷史——只取更舊的訊息、仍最近先。"""
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公")
    store.seed_turn("e1", "user", "早安", 10.0)
    store.seed_turn("e1", "assistant", "阿公早", 20.0)
    store.seed_reminder("e1", "medication", "早上用藥提醒", 30.0)
    feed = store.list_feed(after=0.0, before=30.0, limit=10)
    assert [i.created_at for i in feed] == [20.0, 10.0]


def test_list_timeline_includes_voice_cards_in_time_order():
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公")
    store.seed_binding("U1", "e1")
    store.now = 10.0
    store.record_asr_call(
        trace_id="t1",
        external_id="U1",
        status="ok",
        latency_ms=1,
        transcript="早安",
        source_audio_url="https://x/in.m4a",
        error_message="",
    )
    store.seed_turn("e1", "user", "早安", 11.0)
    store.seed_turn("e1", "assistant", "阿公早", 12.0)
    store.now = 13.0
    store.record_reply(
        trace_id="t1",
        external_id="U1",
        kind="voice",
        status="ok",
        latency_ms=1,
        audio_url="https://x/out.m4a",
    )
    store.seed_risk("e2", 3, "別人的事件", 12.5)  # 不同長輩，不應出現
    items = store.list_timeline_for_elder(elder_id="e1", start=0.0, end=100.0)
    assert [i.kind for i in items] == ["voice", "turn", "turn", "voice"]
    assert items[0].trace_id == "t1" and items[0].audio_url == "https://x/in.m4a"
    assert items[3].role == "assistant" and items[3].audio_url == "https://x/out.m4a"


def test_list_elders_with_last_active():
    store = FakeTraceStore()
    store.seed_elder("e1", "阿公")
    store.seed_elder("e2", "阿嬤")
    store.seed_binding("U1", "e1")
    store.seed_turn("e1", "user", "hi", 5.0)
    store.seed_turn("e1", "user", "hi2", 9.0)
    elders = store.list_elders_with_last_active()
    by_id = {e.elder_id: e for e in elders}
    assert by_id["e1"].last_active_at == 9.0
    assert by_id["e1"].bound_channels == "line"
    assert by_id["e2"].last_active_at is None
    assert by_id["e2"].bound_channels == ""


def test_overview_stats_counts_and_stage_errors():
    store = FakeTraceStore()
    store.seed_turn("e1", "user", "a", 100.0)
    store.seed_turn("e1", "assistant", "b", 101.0)
    store.seed_turn("e2", "user", "c", 102.0)
    store.seed_turn("e1", "user", "舊資料", 1.0)  # today_start 之前，不計
    store.seed_risk("e1", 2, "頭暈", 105.0)
    store.now = 110.0
    store.record_asr_call(
        trace_id="t1",
        external_id="U1",
        status="ok",
        latency_ms=100,
        transcript="a",
        source_audio_url="",
        error_message="",
    )
    store.record_asr_call(
        trace_id="t2",
        external_id="U2",
        status="error",
        latency_ms=300,
        transcript="",
        source_audio_url="",
        error_message="逾時",
    )
    stats = store.get_overview_stats(today_start=50.0, hourly_start=50.0)
    assert stats.turn_count == 3
    assert stats.active_elder_count == 2
    assert stats.risk_event_count == 1
    asr = next(s for s in stats.stages if s.stage == "asr")
    assert (asr.call_count, asr.error_count) == (2, 1)
    assert asr.avg_latency_ms == 200.0
    assert asr.p50_latency_ms == 100.0  # nearest-rank：⌈0.5×2⌉＝第 1 筆
    assert sum(h.turn_count for h in stats.hourly_turns) == 3


def test_overview_stats_round_trip_stage_p50_p95():
    """✅ D-05（戊-2）：語音往返延遲 P50／P95——round_trip_ms 為 NULL（未量測）不計。"""
    store = FakeTraceStore()
    store.now = 100.0
    for ms in (700, 900, 1400):
        store.record_reply(
            trace_id="t",
            external_id="U1",
            kind="voice",
            status="ok",
            latency_ms=100,
            round_trip_ms=ms,
            audio_url="",
        )
    store.record_reply(
        trace_id="t",
        external_id="U1",
        kind="text",
        status="ok",
        latency_ms=5,
        round_trip_ms=None,
        audio_url="",
    )
    stats = store.get_overview_stats(today_start=50.0, hourly_start=50.0)
    round_trip = next(s for s in stats.stages if s.stage == "round_trip")
    assert round_trip.call_count == 3
    assert round_trip.avg_latency_ms == 1000.0
    assert round_trip.p50_latency_ms == 900.0
    assert round_trip.p95_latency_ms == 1400.0


def test_purge_only_removes_old_observability_rows():
    store = FakeTraceStore()
    store.now = 10.0
    store.record_reply(
        trace_id="t1", external_id="U1", kind="text", status="ok", latency_ms=1, audio_url=""
    )
    store.now = 90.0
    store.record_reply(
        trace_id="t2", external_id="U1", kind="text", status="ok", latency_ms=1, audio_url=""
    )
    store.seed_turn("U1", "user", "對話不清", 10.0)
    store.purge_older_than(50.0)
    assert [r.trace_id for r in store.replies] == ["t2"]
    assert len(store.turns) == 1  # 既有表不在清理範圍
