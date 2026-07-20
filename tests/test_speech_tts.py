import pytest

from kinsun.speech.tts import DgxTtsClient, TextBubbleTts, TTSError, TtsResult, build_tts_client
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


def test_build_dgx_returns_client():
    client = build_tts_client(_StubSettings(backend="dgx", endpoint="http://dgx:8002/synthesize"))
    assert isinstance(client, DgxTtsClient)
