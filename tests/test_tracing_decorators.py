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


def test_current_opik_trace_id_empty_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.current_opik_trace_id() == ""


def test_current_opik_trace_id_returns_id_when_enabled(monkeypatch):
    from types import SimpleNamespace

    import opik

    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(
        opik.opik_context, "get_current_trace_data", lambda: SimpleNamespace(id="opik-trace-123")
    )
    assert tracing.current_opik_trace_id() == "opik-trace-123"


def test_current_opik_trace_id_empty_when_no_current_trace(monkeypatch):
    import opik

    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik.opik_context, "get_current_trace_data", lambda: None)
    assert tracing.current_opik_trace_id() == ""


def test_opik_trace_url_empty_for_missing_inputs():
    assert tracing.opik_trace_url("", "http://localhost:5273/api") == ""
    assert tracing.opik_trace_url("abc", "") == ""


def test_opik_trace_url_builds_redirect_link():
    url = tracing.opik_trace_url("trace-abc", "http://localhost:5273/api")
    assert url.startswith("http://localhost:5273/api")
    assert "redirect/projects" in url
    assert "trace_id=trace-abc" in url


def _spy_prompt(monkeypatch) -> tuple[list, list]:
    """啟用工程觀測、攔截 opik.Prompt 建構與 attach_prompt_to_current_trace（hermetic）。"""
    import opik

    from kinsun.tracing import decorators

    decorators._prompt_cache.clear()
    constructed: list[dict] = []
    attached: list = []
    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik, "Prompt", lambda **kw: constructed.append(kw) or f"P:{kw['name']}")
    monkeypatch.setattr(
        opik.opik_context, "attach_prompt_to_current_trace", lambda p: attached.append(p)
    )
    return constructed, attached


def test_attach_prompt_noop_when_disabled():
    tracing_client.reset_for_test()
    assert tracing.attach_prompt("care_system", "你好") is None


def test_attach_prompt_registers_and_links_when_enabled(monkeypatch):
    constructed, attached = _spy_prompt(monkeypatch)
    tracing.attach_prompt("care_system", "你是金孫")
    assert constructed == [
        {"name": "care_system", "prompt": "你是金孫", "validate_placeholders": False}
    ]
    assert attached == ["P:care_system"]


def test_attach_prompt_caches_unchanged_content_but_relinks_each_call(monkeypatch):
    """同名同內容不重覆建版（省後端往返），但每輪仍連結到當前 trace。"""
    constructed, attached = _spy_prompt(monkeypatch)
    tracing.attach_prompt("care_system", "同一段 prompt")
    tracing.attach_prompt("care_system", "同一段 prompt")
    assert len(constructed) == 1
    assert len(attached) == 2


def test_attach_prompt_new_version_when_content_changes(monkeypatch):
    constructed, _ = _spy_prompt(monkeypatch)
    tracing.attach_prompt("care_system", "第一版")
    tracing.attach_prompt("care_system", "第二版")
    assert [c["prompt"] for c in constructed] == ["第一版", "第二版"]
