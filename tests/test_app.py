"""web 組裝根：build_app 的整體接線煙霧測試（M-8 覆蓋補強）。

外部相依以假 Externals 替換，其餘接線（pipeline／閘門／routers／信封／
安全標頭）照常執行——驗證「app 建得起來、該掛的端點有掛」。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import kinsun.app as app_module
from kinsun.composition import Externals

_REQUIRED_ENV = {
    "LINE_CHANNEL_SECRET": "test-secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
    "GEMINI_API_KEY": "test-key",
    "DATABASE_URL": "postgresql://unused/unused",
    "ADMIN_API_KEY": "test-admin-key",
    # 固定為離線可組裝的形態：不建音檔託管、不掛 rich menu。
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_KEY": "",
    "TTS_BACKEND": "bubble",
    "RICH_MENU_ID": "",
}


class _FakeDb:
    def close(self) -> None:
        pass


class _FakeLLM:
    def generate(self, *, system_prompt, messages):
        return "好"

    def generate_tool_turn(self, **kwargs):
        raise NotImplementedError


def _build_app(monkeypatch):
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        app_module,
        "build_externals",
        lambda settings: Externals(
            db=_FakeDb(), gemini=_FakeLLM(), long_term=object(), messenger=object()
        ),
    )
    return app_module.build_app()


def test_build_app_serves_healthz(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_build_app_mounts_v1_routers(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        paths = set(client.get("/openapi.json").json()["paths"])
    assert "/api/v1/turns" in paths  # App 對講機
    assert "/api/v1/admin/overview" in paths  # 觀測後台
    assert any(path.startswith("/api/v1/") and "elders" in path for path in paths)  # 家屬面


def test_build_app_wires_show_transcript_to_every_voice_delivery(monkeypatch):
    """ASR_DEBUG_SHOW_TRANSCRIPT 必須同時作用於 LINE 與 App 兩通道：App 對講機的
    VoiceReplyDelivery 是獨立實例，漏傳旗標會讓 debug 模式只有 LINE 看得到辨識文字、
    App 只剩回覆文字（2026-07-19 實錄）。"""
    captured: list[bool] = []

    class _SpyDelivery(app_module.VoiceReplyDelivery):
        def __init__(self, *args, **kwargs):
            captured.append(bool(kwargs.get("show_transcript", False)))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(app_module, "VoiceReplyDelivery", _SpyDelivery)
    monkeypatch.setenv("ASR_DEBUG_SHOW_TRANSCRIPT", "1")
    _build_app(monkeypatch)
    assert captured, "build_app 應至少建構一個 VoiceReplyDelivery"
    assert all(captured), f"有 VoiceReplyDelivery 漏傳 show_transcript：{captured}"


def test_build_app_installs_security_headers_and_envelope(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        res = client.get("/api/v1/admin/overview")  # 未帶金鑰 → 401 統一信封
    assert res.status_code == 401
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"]
    assert "content-security-policy" in res.headers
