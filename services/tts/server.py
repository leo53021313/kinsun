"""DGX 端 TTS 推論服務（CosyVoice 3）：提供 POST /synthesize、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/tts/requirements.txt。
啟動：uvicorn services.tts.server:app --host 0.0.0.0 --port 8002

與 kinsun.speech.tts.DgxTtsClient 的契約：
- 輸入：JSON {"text": "繁體國語漢字"}。
- 輸出：m4a（AAC）bytes、Content-Type: audio/mp4、header X-Duration-Ms。

zero-shot 聲音複製：TTS_PROMPT_WAV（參考音檔）＋ TTS_PROMPT_TEXT（其逐字稿）。

DGX 實機鎖定（2026-07-02，GB10 / aarch64 / CUDA 13）：
- CosyVoice repo 非 pip 套件，須把 repo 與其 third_party/Matcha-TTS 加入 sys.path
  （TTS_COSY_DIR／TTS_MATCHA_DIR）。
- aarch64 上 torchaudio 的 load/save 會強走 torchcodec（.so 載不起來）→ 以 soundfile 包一層。
- 用 AutoModel 依模型目錄自動判別（Fun-CosyVoice3-0.5B-2512 → CosyVoice3）。
- zero-shot 逐字稿須加 instruct 前綴 "You are a helpful assistant.<|endofprompt|>"，
  否則 LLM 會立刻 EOS、產不出語音。
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

TTS_MODEL_ID = os.environ.get("TTS_MODEL_ID", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
TTS_COSY_DIR = os.environ.get("TTS_COSY_DIR", "")
TTS_MATCHA_DIR = os.environ.get("TTS_MATCHA_DIR", "")
TTS_PROMPT_WAV = os.environ.get("TTS_PROMPT_WAV", "")
TTS_PROMPT_TEXT = os.environ.get("TTS_PROMPT_TEXT", "")
TTS_MAX_CONCURRENCY = int(os.environ.get("TTS_MAX_CONCURRENCY", "1"))
TTS_MAX_QUEUE = int(os.environ.get("TTS_MAX_QUEUE", "8"))
TTS_PRELOAD = os.environ.get("TTS_PRELOAD", "0").strip().lower() not in {"0", "false", "no", ""}

# zero-shot 逐字稿的 instruct 前綴（見模組 docstring 的 DGX 鎖定說明）。
_INSTRUCT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

_model = None
_sem = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
_inflight = 0


def _install_soundfile_shim() -> None:
    """aarch64：用 soundfile 取代 torchaudio 的 load/save（torchcodec .so 載不起來）。"""
    import soundfile as sf
    import torch
    import torchaudio

    def _sf_load(filepath, *a, **k):
        data, srate = sf.read(str(filepath), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T).contiguous(), srate

    def _sf_save(filepath, src, sample_rate, *a, **k):
        sf.write(str(filepath), src.detach().cpu().numpy().T, sample_rate)

    torchaudio.load = _sf_load
    torchaudio.save = _sf_save


def _get_model():
    """延遲載入 CosyVoice 3；缺參考語音或 repo 路徑設定即明確報錯。"""
    global _model
    if _model is None:
        if not TTS_PROMPT_WAV or not TTS_PROMPT_TEXT:
            raise RuntimeError("需設定 TTS_PROMPT_WAV 與 TTS_PROMPT_TEXT（金孫參考語音）")
        if not TTS_COSY_DIR:
            raise RuntimeError("需設定 TTS_COSY_DIR（CosyVoice repo 目錄）")
        matcha_dir = TTS_MATCHA_DIR or os.path.join(TTS_COSY_DIR, "third_party", "Matcha-TTS")
        for path in (matcha_dir, TTS_COSY_DIR):
            if path not in sys.path:
                sys.path.insert(0, path)
        _install_soundfile_shim()
        from cosyvoice.cli.cosyvoice import AutoModel

        _model = AutoModel(model_dir=TTS_MODEL_ID)
    return _model


def _synthesize(text: str) -> tuple[bytes, int]:
    import soundfile as sf
    import torch

    model = _get_model()
    prompt = f"{_INSTRUCT_PREFIX}{TTS_PROMPT_TEXT}"
    chunks = [
        out["tts_speech"]
        for out in model.inference_zero_shot(text, prompt, TTS_PROMPT_WAV, stream=False)
    ]
    if not chunks:
        raise RuntimeError("CosyVoice 3 未產出任何語音段")
    waveform = torch.cat(chunks, dim=1)  # [1, N]
    sample_rate = int(model.sample_rate)
    duration_ms = int(waveform.shape[1] / sample_rate * 1000)

    wav_buf = io.BytesIO()
    sf.write(wav_buf, waveform.detach().cpu().numpy().T, sample_rate, format="WAV")
    return _wav_to_m4a(wav_buf.getvalue()), duration_ms


def _wav_to_m4a(wav_bytes: bytes) -> bytes:
    """DGX 端 ffmpeg：wav → AAC/m4a（應用層跨平台、不裝 ffmpeg）。

    mp4/m4a 的 moov atom 需可 seek 的輸出，直接寫 pipe:1 會失敗
    （muxer does not support non seekable output）→ 走可 seek 的暫存檔再讀回。
    """
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0", "-c:a", "aac", tmp_path],
            input=wav_bytes,
            capture_output=True,
            check=True,
        )
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(tmp_path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if TTS_PRELOAD:
        _get_model()
    yield


app = FastAPI(title="KinSun TTS (CosyVoice 3)", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "model_loaded": _model is not None}


@app.post("/synthesize")
async def synthesize(payload: dict) -> Response:
    global _inflight
    if _inflight >= TTS_MAX_CONCURRENCY + TTS_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="TTS 過載，請稍後再試")
    _inflight += 1
    try:
        async with _sem:
            audio, duration_ms = await run_in_threadpool(_synthesize, payload.get("text", ""))
    finally:
        _inflight -= 1
    return Response(
        content=audio,
        media_type="audio/mp4",
        headers={"X-Duration-Ms": str(duration_ms)},
    )
