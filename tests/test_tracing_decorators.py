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

    monkeypatch.setattr(opik, "track", lambda **kw: (lambda f: f))
    monkeypatch.setattr(tracing_client, "is_enabled", lambda: True)
    assert g(41) == 42


def test_tag_current_trace_noop_when_disabled():
    tracing_client.reset_for_test()
    # 停用時純 no-op、不得拋例外。
    assert tracing.tag_current_trace(trace_id="abc", channel="line") is None
