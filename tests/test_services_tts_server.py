"""DGX TTS 服務的離線測試（✅ 庚-24／A-13）：金鑰、請求驗證、併發閘、回應契約。

模型推論需 GPU＋CosyVoice repo，但這些純邏輯不需要——以 monkeypatch 換掉
`_synthesize`，在無 GPU 的 CI 上鎖住服務層行為與回應契約
（audio/mp4＋X-Duration-Ms，對應 kinsun.speech.tts.DgxTtsClient）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.tts import server as tts_server


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        tts_server, "_synthesize", lambda text, prompt_wav, prompt_text: (b"fake-m4a", 1234)
    )
    return TestClient(tts_server.app)


def test_healthz_reports_model_not_loaded(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model_loaded": False}


def test_synthesize_contract_media_type_and_duration_header(client):
    res = client.post("/synthesize", json={"text": "阿公早安"})
    assert res.status_code == 200
    assert res.content == b"fake-m4a"
    assert res.headers["content-type"] == "audio/mp4"
    assert res.headers["X-Duration-Ms"] == "1234"


def test_synthesize_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_API_KEY", "sekret")
    no_key = client.post("/synthesize", json={"text": "哈囉"})
    ok = client.post("/synthesize", json={"text": "哈囉"}, headers={"X-Api-Key": "sekret"})
    assert no_key.status_code == 401
    assert ok.status_code == 200


def test_synthesize_rejects_missing_or_blank_text(client):
    assert client.post("/synthesize", json={}).status_code == 400
    res = client.post("/synthesize", json={"text": "  "})
    assert res.status_code == 400
    assert res.json()["detail"] == "missing_text"


def test_synthesize_rejects_overlong_text(client, monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_MAX_TEXT_CHARS", 5)
    res = client.post("/synthesize", json={"text": "六個字的長句子"})
    assert res.status_code == 413
    assert res.json()["detail"] == "text_too_long"


def test_synthesize_sheds_load_when_queue_full(client, monkeypatch):
    monkeypatch.setattr(
        tts_server, "_inflight", tts_server.TTS_MAX_CONCURRENCY + tts_server.TTS_MAX_QUEUE
    )
    res = client.post("/synthesize", json={"text": "哈囉"})
    assert res.status_code == 503
    assert res.json()["detail"] == "overloaded"


def test_synthesize_passes_elder_voice_fields_through(client, monkeypatch):
    """長輩客製化聲音複製（2026-07-30）：/synthesize 收到 elder_id 等欄位時，
    會轉交給 _resolve_voice 解析出實際要用的參考音檔／逐字稿。"""
    calls = []

    def fake_resolve_voice(elder_id, prompt_audio_url, prompt_text):
        calls.append((elder_id, prompt_audio_url, prompt_text))
        return "/cached/e1.wav", "客製逐字稿"

    monkeypatch.setattr(tts_server, "_resolve_voice", fake_resolve_voice)
    res = client.post(
        "/synthesize",
        json={
            "text": "哈囉",
            "elder_id": "e1",
            "prompt_audio_url": "https://example.test/e1.wav",
            "prompt_text": "客製逐字稿",
        },
    )
    assert res.status_code == 200
    assert calls == [("e1", "https://example.test/e1.wav", "客製逐字稿")]


class _FakeHttpResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resolve_voice_without_elder_id_returns_global_default(monkeypatch):
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")
    assert tts_server._resolve_voice("", "", "") == ("/default.wav", "預設逐字稿")


def test_resolve_voice_falls_back_when_no_cache_and_no_url(monkeypatch):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")
    assert tts_server._resolve_voice("e1", "", "") == ("/default.wav", "預設逐字稿")


def test_resolve_voice_downloads_once_then_reuses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    calls = []

    def fake_urlopen(url):
        calls.append(url)
        return _FakeHttpResponse(b"WAVDATA")

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", fake_urlopen)

    wav_path, text = tts_server._resolve_voice("e1", "https://example.test/v.wav", "逐字稿")
    assert text == "逐字稿"
    assert (tmp_path / "voice-e1.wav").read_bytes() == b"WAVDATA"
    assert len(calls) == 1

    # 第二次同一個 elder_id：命中快取，不重新下載（即便沒再帶 prompt_audio_url）。
    wav_path2, text2 = tts_server._resolve_voice("e1", "", "")
    assert wav_path2 == wav_path
    assert text2 == "逐字稿"
    assert len(calls) == 1


def test_resolve_voice_cache_evicts_oldest_when_full(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_SIZE", 1)
    monkeypatch.setattr(tts_server.urllib.request, "urlopen", lambda url: _FakeHttpResponse(b"W"))

    tts_server._resolve_voice("e1", "https://example.test/e1.wav", "e1 逐字稿")
    tts_server._resolve_voice("e2", "https://example.test/e2.wav", "e2 逐字稿")
    assert "e1" not in tts_server._voice_cache
    assert "e2" in tts_server._voice_cache


def test_resolve_voice_falls_back_when_download_fails(monkeypatch, tmp_path):
    """下載失敗只犧牲客製化聲音，不能讓整輪沒聲音（2026-08-01）。

    原本 urlopen 未接例外：網址過期／Supabase 不通都會讓 /synthesize 回 500，
    應用層據此退化成純文字——長輩完全聽不到聲音，而且每輪重複發生（快取永遠暖不起來）。
    客製化聲音失效是缺憾，沒聲音是故障，兩者嚴重度差一級。
    """
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    def boom(_url):
        raise OSError("HTTP Error 400: Bad Request")  # 簽章網址過期時 Supabase 的回應

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", boom)

    assert tts_server._resolve_voice("e1", "https://expired.test/v.wav", "逐字稿") == (
        "/default.wav",
        "預設逐字稿",
    )


def test_resolve_voice_does_not_cache_a_failed_download(monkeypatch, tmp_path):
    """失敗不入快取：下次（例如網址已換發）要能再試，否則一次失敗就永久退化。"""
    monkeypatch.setattr(tts_server, "_voice_cache", {})
    monkeypatch.setattr(tts_server, "TTS_VOICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tts_server, "TTS_PROMPT_WAV", "/default.wav")
    monkeypatch.setattr(tts_server, "TTS_PROMPT_TEXT", "預設逐字稿")

    attempts = []

    def flaky(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise OSError("暫時失敗")
        return _FakeHttpResponse(b"WAVDATA")

    monkeypatch.setattr(tts_server.urllib.request, "urlopen", flaky)

    first = tts_server._resolve_voice("e1", "https://x.test/v.wav", "逐字稿")
    assert first == ("/default.wav", "預設逐字稿")

    second = tts_server._resolve_voice("e1", "https://x.test/v.wav", "逐字稿")
    assert second == (str(tmp_path / "voice-e1.wav"), "逐字稿")
    assert len(attempts) == 2
