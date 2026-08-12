import json

import pytest

from kinsun.speech.tts import (
    DgxTtsClient,
    QueuedTtsClient,
    TextBubbleTts,
    TTSError,
    TtsResult,
    VoiceReference,
    build_tts_client,
)
from kinsun.transport import FakeTransport, Response, TransportError


def test_text_bubble_returns_text_without_audio():
    result = TextBubbleTts().synthesize("阿公您好")
    assert isinstance(result, TtsResult)
    assert result.text == "阿公您好"
    assert result.audio is None


class _StubSettings:
    def __init__(self, backend="bubble", endpoint="", timeout=30.0):
        self.tts_backend = backend
        self.tts_endpoint = endpoint
        self.tts_timeout_seconds = timeout
        self.tts_api_key = ""


def test_dgx_tts_returns_audio_and_duration():
    transport = FakeTransport([Response(200, {"X-Duration-Ms": "1234"}, b"AUDIOBYTES")])
    client = DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport)
    result = client.synthesize("阿公您好")
    assert result.text == "阿公您好"
    assert result.audio == b"AUDIOBYTES"
    assert result.duration_ms == 1234
    method, url, data, headers, timeout = transport.calls[0]
    assert (method, url, timeout) == ("POST", "http://dgx:8002/synthesize", 30.0)
    assert "阿公".encode() in data  # JSON body 帶 text
    assert headers["Content-Type"] == "application/json"


def test_dgx_tts_reads_duration_header_case_insensitively():
    """真實線路 regression（2026-07-18）：uvicorn/Starlette 送出的標頭名一律小寫，
    大小寫敏感查找會把每一輪 TTS 都誤判成缺標頭、全數退化成純文字。"""
    transport = FakeTransport([Response(200, {"x-duration-ms": "680"}, b"AUDIOBYTES")])
    client = DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport)
    result = client.synthesize("阿公您好")
    assert result.audio == b"AUDIOBYTES"
    assert result.duration_ms == 680


def test_dgx_tts_missing_duration_header_raises():
    transport = FakeTransport([Response(200, {}, b"A")])
    with pytest.raises(TTSError):
        DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport).synthesize("嗨")


def test_dgx_tts_transport_error_raises():
    transport = FakeTransport()
    transport.error = TransportError("connection refused")
    with pytest.raises(TTSError):
        DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport).synthesize("嗨")


def test_build_returns_bubble_by_default():
    assert isinstance(build_tts_client(_StubSettings()), TextBubbleTts)


def test_build_dgx_without_endpoint_raises():
    with pytest.raises(TTSError):
        build_tts_client(_StubSettings(backend="dgx", endpoint=""))


def test_build_dgx_returns_a_queued_dgx_client():
    """dgx 後端必須被優先權佇列包起來（spec 2026-07-28 P1）：瓶頸是那顆 GB10，
    併發合成會互搶且搶得沒有規律（實測同一段落某次 1.88s、另一次 15.08s）。"""
    client = build_tts_client(_StubSettings(backend="dgx", endpoint="http://dgx:8002/synthesize"))
    assert isinstance(client, QueuedTtsClient)
    assert isinstance(client._inner, DgxTtsClient)
    client.close()


def test_build_bubble_is_not_queued():
    """文字泡泡沒有 GPU，包了只是多一層執行緒——本機開發與單元測試不該付這個成本。"""
    client = build_tts_client(_StubSettings(backend="bubble", endpoint=""))
    assert not isinstance(client, QueuedTtsClient)


def test_dgx_tts_without_voice_sends_only_text():
    """向下相容：不帶 voice 時，JSON body 只有 text，不含 elder_id 等客製化欄位。"""
    transport = FakeTransport([Response(200, {"X-Duration-Ms": "1234"}, b"AUDIOBYTES")])
    client = DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport)
    client.synthesize("阿公您好")
    _, _, data, _, _ = transport.calls[0]
    assert json.loads(data) == {"text": "阿公您好"}


def test_dgx_tts_with_voice_includes_reference_fields():
    """長輩客製化聲音複製（2026-07-30）：帶 voice 時 JSON body 含 elder_id／
    prompt_audio_url／prompt_text／prompt_version。

    ⚠️ `prompt_version` 不可省（2026-08-12）：DGX 端靠它分辨「家屬重錄過了」，
    少了它就會一直用第一次下載的那份錄音，而且不會有任何錯誤訊息。
    """
    transport = FakeTransport([Response(200, {"X-Duration-Ms": "1234"}, b"AUDIOBYTES")])
    client = DgxTtsClient("http://dgx:8002/synthesize", 30.0, transport=transport)
    voice = VoiceReference(
        elder_id="e1",
        prompt_audio_url="https://example.test/v.wav",
        prompt_text="逐字稿",
        version="1754870400.0",
    )
    client.synthesize("阿公您好", voice=voice)
    _, _, data, _, _ = transport.calls[0]
    assert json.loads(data) == {
        "text": "阿公您好",
        "elder_id": "e1",
        "prompt_audio_url": "https://example.test/v.wav",
        "prompt_text": "逐字稿",
        "prompt_version": "1754870400.0",
    }
