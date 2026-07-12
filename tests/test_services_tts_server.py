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
    monkeypatch.setattr(tts_server, "_synthesize", lambda text: (b"fake-m4a", 1234))
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
