from kinsun import tracing
from kinsun.tracing import client as tracing_client


def test_track_is_identity_when_disabled():
    tracing_client.reset_for_test()  # 停用
    calls = []

    @tracing.track(name="x")
    def f(a):
        calls.append(a)
        return a * 2

    assert f(3) == 6
    assert calls == [3]


def test_track_defers_enable_check_to_call_time(monkeypatch):
    # 裝飾時停用、呼叫時啟用：仍應正常執行原邏輯（此處驗證不炸、回傳正確）。
    tracing_client.reset_for_test()

    @tracing.track(name="y")
    def g(a):
        return a + 1

    # 單元測試須 hermetic：用假的 opik.track（回傳 identity 裝飾器）取代真 SDK，
    # 避免啟用時真的初始化 Opik client 去連線。
    import opik

    monkeypatch.setattr(opik, "track", lambda **kw: lambda f: f)
    monkeypatch.setattr(tracing_client, "is_enabled", lambda: True)
    assert g(41) == 42


def test_tag_current_trace_noop_when_disabled():
    tracing_client.reset_for_test()
    # 停用時純 no-op、不得拋例外。
    assert tracing.tag_current_trace(trace_id="abc", channel="line") is None


def test_update_trace_metadata_noop_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.update_trace_metadata(tier="L2") is None


def test_log_feedback_score_noop_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.log_feedback_score("helpful", 1.0) is None


def test_tag_current_trace_accepts_extra_metadata_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.tag_current_trace(trace_id="t", channel="line", elder_id="e", tier="L1") is None


def test_set_current_trace_io_noop_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.set_current_trace_io(user_input="嗨", assistant_output="你好") is None


def _spy_update_current_trace(monkeypatch) -> list[dict]:
    """啟用工程觀測、攔截 update_current_trace 呼叫（hermetic，不連 Opik）。"""
    import opik

    calls: list[dict] = []
    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik.opik_context, "update_current_trace", lambda **kw: calls.append(kw))
    return calls


def test_set_current_trace_io_writes_input_and_output_when_enabled(monkeypatch):
    calls = _spy_update_current_trace(monkeypatch)
    tracing.set_current_trace_io(user_input="阿公早安", assistant_output="早安，您今天好嗎")
    assert calls == [{"input": {"text": "阿公早安"}, "output": {"text": "早安，您今天好嗎"}}]


def test_set_current_trace_io_skips_empty_input(monkeypatch):
    """靜音誤觸沒有可顯示的原話：只寫 output、不寫空 input。"""
    calls = _spy_update_current_trace(monkeypatch)
    tracing.set_current_trace_io(user_input="", assistant_output="請再說一次好嗎")
    assert calls == [{"output": {"text": "請再說一次好嗎"}}]


def test_set_current_trace_io_noop_on_both_empty(monkeypatch):
    calls = _spy_update_current_trace(monkeypatch)
    tracing.set_current_trace_io(user_input="", assistant_output="")
    assert calls == []


def _spy_update_current_span(monkeypatch) -> list[dict]:
    """啟用工程觀測、攔截 update_current_span 呼叫（hermetic，不連 Opik）。"""
    import opik

    calls: list[dict] = []
    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik.opik_context, "update_current_span", lambda **kw: calls.append(kw))
    return calls


def test_set_current_span_io_noop_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.set_current_span_io(span_output={"summary": "今天很好"}) is None


def test_set_current_span_io_writes_input_and_output_when_enabled(monkeypatch):
    calls = _spy_update_current_span(monkeypatch)
    tracing.set_current_span_io(span_input={"messages": ["嗨"]}, span_output={"summary": "很好"})
    assert calls == [{"input": {"messages": ["嗨"]}, "output": {"summary": "很好"}}]


def test_set_current_span_io_skips_none(monkeypatch):
    calls = _spy_update_current_span(monkeypatch)
    tracing.set_current_span_io(span_output={"strategies": []})
    assert calls == [{"output": {"strategies": []}}]


def test_set_current_span_io_noop_on_both_none(monkeypatch):
    calls = _spy_update_current_span(monkeypatch)
    tracing.set_current_span_io()
    assert calls == []
