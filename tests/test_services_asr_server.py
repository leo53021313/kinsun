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


def test_transcribe_silent_audio_returns_empty_without_model(monkeypatch):
    """純靜音不得進模型（2026-07-18 實錄）：誤觸的 0.35 秒空錄音（全零樣本）會讓
    Whisper 系模型確定性幻覺出「來，請坐…」重複迴圈直到 token 上限，一輪燒約
    10 秒 GPU，還污染下游回覆與風險分級。靜音直接回空字串。"""
    import numpy as np

    monkeypatch.setattr(
        asr_server, "_decode_to_mono16k", lambda audio: np.zeros(16000, dtype=np.float32)
    )

    def boom():
        raise AssertionError("靜音不得進模型")

    monkeypatch.setattr(asr_server, "_get_model", boom)
    assert asr_server._transcribe(b"\x00\x01") == ""


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


# ── 語言必須釘死（V-01，2026-07-29）─────────────────────────────────────


def _spy_model(monkeypatch, recorded: dict, text: str = "早安"):
    """換掉重模型：記下呼叫時帶的 generate_kwargs，不需要 GPU。"""
    import numpy as np

    monkeypatch.setattr(
        asr_server, "_decode_to_mono16k", lambda audio: np.ones(16000, dtype=np.float32)
    )

    def model(payload, **kwargs):
        recorded.update(kwargs)
        return {"text": text}

    monkeypatch.setattr(asr_server, "_get_model", lambda: model)


def test_transcribe_pins_the_language_instead_of_auto_detecting(monkeypatch):
    """⚠️ 這是 V-01 幻覺的根因修正，不是可有可無的調校。

    模型的 `generation_config.forced_decoder_ids` 是 `[[1, None], [2, 50359]]`——
    位置 2 釘住 `<|transcribe|>`，位置 1（語言）卻是 **None**，於是每一次請求都先跑
    一次自動語言偵測。音檔清楚時偵測得準；近無聲或尾端帶靜音時偵測結果是垃圾，
    解碼隨即跑進退化迴圈。

    2026-07-29 實測（真模型、同檔各 6 次）：不釘語言 **6/6** 把 0.76 秒的「早安」
    辨識成「晴文」重複 60 次——那串字會進危急分級器，實錄曾因此**真的送出假警報
    給家屬**；釘住語言後 **0/6**。純白噪音也從立陶宛人名「Vytautas」收斂成中文短字。
    """
    recorded: dict = {}
    _spy_model(monkeypatch, recorded)
    assert asr_server._transcribe(b"\x00\x01") == "早安"
    assert recorded["generate_kwargs"] == {"language": "zh", "task": "transcribe"}


def test_empty_asr_language_restores_auto_detection(monkeypatch):
    """逃生口：`ASR_LANGUAGE=""` 回到自動偵測（＝修正前行為）。

    改不動語音模型時要有辦法就地回退，不必重新部署程式。
    """
    recorded: dict = {}
    _spy_model(monkeypatch, recorded)
    monkeypatch.setattr(asr_server, "ASR_LANGUAGE", "")
    asr_server._transcribe(b"\x00\x01")
    assert "generate_kwargs" not in recorded


def test_asr_language_is_configurable(monkeypatch):
    """語言可換（如日後要跑純英文或其他語系），但預設必須是中文。"""
    recorded: dict = {}
    _spy_model(monkeypatch, recorded)
    monkeypatch.setattr(asr_server, "ASR_LANGUAGE", "en")
    asr_server._transcribe(b"\x00\x01")
    assert recorded["generate_kwargs"] == {"language": "en", "task": "transcribe"}


def test_silent_audio_still_skips_the_model_entirely(monkeypatch):
    """釘語言不可讓靜音閘失效：那道閘省的是整整一輪 GPU，仍必須排在最前面。"""
    import numpy as np

    monkeypatch.setattr(
        asr_server, "_decode_to_mono16k", lambda audio: np.zeros(16000, dtype=np.float32)
    )

    def boom():
        raise AssertionError("靜音不得進模型")

    monkeypatch.setattr(asr_server, "_get_model", boom)
    assert asr_server._transcribe(b"\x00\x01") == ""
