"""DGX ASR 服務的離線測試（✅ 庚-24／A-13）：金鑰、請求驗證、併發閘、healthz。

模型推論需 GPU，但這些純邏輯不需要——以 monkeypatch 換掉 `_transcribe`，
在無 GPU 的 CI 上鎖住服務層行為。重模型延遲載入，import 本模組不吃 torch。
"""

from __future__ import annotations

import logging
import subprocess

import pytest
from fastapi.testclient import TestClient

from services.asr import server as asr_server


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(asr_server, "_transcribe", lambda audio: "阿公早安")
    return TestClient(asr_server.app)


def test_healthz_reports_model_not_loaded(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model_loaded": False}


def test_transcribe_happy_path_without_key_mode(client):
    res = client.post("/transcribe", content=b"\x00\x01", headers={"content-type": "audio/m4a"})
    assert res.status_code == 200
    assert res.json() == {"text": "阿公早安"}


def test_transcribe_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(asr_server, "ASR_API_KEY", "sekret")
    no_key = client.post("/transcribe", content=b"\x00")
    wrong = client.post("/transcribe", content=b"\x00", headers={"X-Api-Key": "nope"})
    ok = client.post("/transcribe", content=b"\x00", headers={"X-Api-Key": "sekret"})
    assert no_key.status_code == 401
    assert wrong.status_code == 401
    assert ok.status_code == 200


def test_transcribe_rejects_empty_body(client):
    res = client.post("/transcribe", content=b"")
    assert res.status_code == 400
    assert res.json()["detail"] == "missing_audio"


def test_transcribe_rejects_oversized_body(client, monkeypatch):
    monkeypatch.setattr(asr_server, "ASR_MAX_BODY_BYTES", 4)
    res = client.post("/transcribe", content=b"\x00" * 5)
    assert res.status_code == 413
    assert res.json()["detail"] == "audio_too_large"


def test_decode_failure_raises_domain_error_and_logs_stderr(monkeypatch, caplog):
    """ffmpeg 解碼失敗須轉成 AudioDecodeError，且 stderr 要進 log（否則根因不可查）。"""

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(183, ["ffmpeg"], stderr=b"moov atom not found")

    monkeypatch.setattr(asr_server.subprocess, "run", fake_run)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(asr_server.AudioDecodeError):
            asr_server._decode_to_mono16k(b"\x00\x01")
    assert "moov atom not found" in caplog.text
    assert "183" in caplog.text


def test_decode_failure_raises_when_no_samples(monkeypatch):
    """ffmpeg 成功但輸出 0 樣本（如 0 秒音檔）也視為解碼失敗，不餵空陣列進模型。"""

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(["ffmpeg"], 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(asr_server.subprocess, "run", fake_run)
    with pytest.raises(asr_server.AudioDecodeError):
        asr_server._decode_to_mono16k(b"\x00\x01")


def test_transcribe_returns_422_when_audio_undecodable(client, monkeypatch):
    def undecodable(audio):
        raise asr_server.AudioDecodeError("ffmpeg exit 183")

    monkeypatch.setattr(asr_server, "_transcribe", undecodable)
    res = client.post("/transcribe", content=b"not-audio")
    assert res.status_code == 422
    assert res.json()["detail"] == "audio_decode_failed"


def test_transcribe_sheds_load_when_queue_full(client, monkeypatch):
    monkeypatch.setattr(
        asr_server, "_inflight", asr_server.ASR_MAX_CONCURRENCY + asr_server.ASR_MAX_QUEUE
    )
    res = client.post("/transcribe", content=b"\x00")
    assert res.status_code == 503
    assert res.json()["detail"] == "overloaded"
