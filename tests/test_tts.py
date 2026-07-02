import io
import urllib.error

import pytest

from kinsun.speech.tts import DgxTtsClient, TTSError, TextBubbleTts, TtsResult, build_tts_client


def test_text_bubble_returns_text_without_audio():
    result = TextBubbleTts().synthesize("阿公您好")
    assert isinstance(result, TtsResult)
    assert result.text == "阿公您好"
    assert result.audio is None


class _FakeResp:
    def __init__(self, body: bytes, duration_ms: str | None):
        self._body = body
        self.headers = {} if duration_ms is None else {"X-Duration-Ms": duration_ms}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _StubSettings:
    def __init__(self, backend="bubble", endpoint="", timeout=30.0):
        self.tts_backend = backend
        self.tts_endpoint = endpoint
        self.tts_timeout_seconds = timeout


def test_dgx_tts_returns_audio_and_duration(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["ctype"] = req.headers.get("Content-type")
        return _FakeResp(b"AUDIOBYTES", "1234")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = DgxTtsClient("http://dgx:8002/synthesize", 30.0)
    result = client.synthesize("阿公您好")
    assert result.text == "阿公您好"
    assert result.audio == b"AUDIOBYTES"
    assert result.duration_ms == 1234
    assert captured["url"] == "http://dgx:8002/synthesize"
    assert "阿公".encode() in captured["body"]  # JSON body 帶 text
    assert captured["ctype"] == "application/json"


def test_dgx_tts_missing_duration_header_raises(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _FakeResp(b"A", None)
    )
    with pytest.raises(TTSError):
        DgxTtsClient("http://dgx:8002/synthesize", 30.0).synthesize("嗨")


def test_dgx_tts_http_error_raises(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(TTSError):
        DgxTtsClient("http://dgx:8002/synthesize", 30.0).synthesize("嗨")


def test_build_returns_bubble_by_default():
    assert isinstance(build_tts_client(_StubSettings()), TextBubbleTts)


def test_build_dgx_without_endpoint_raises():
    with pytest.raises(TTSError):
        build_tts_client(_StubSettings(backend="dgx", endpoint=""))


def test_build_dgx_returns_client():
    client = build_tts_client(_StubSettings(backend="dgx", endpoint="http://dgx:8002/synthesize"))
    assert isinstance(client, DgxTtsClient)
