"""DGX 端 ASR 推論服務：載入 Breeze-ASR-26，提供 POST /transcribe、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/asr/requirements.txt。
啟動：uvicorn services.asr.server:app --host 0.0.0.0 --port 8001

與 kinsun.speech.asr.DgxAsrClient 的契約：
- 輸入：HTTP body 為原始音檔 bytes（Content-Type 由呼叫端帶入）。
- 輸出：JSON {"text": "繁體國語漢字"}。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

# Breeze-ASR-26（Whisper 系）輸入取樣率。
_TARGET_SR = 16000

ASR_MODEL_ID = os.environ.get("ASR_MODEL_ID", "MediaTek-Research/Breeze-ASR-26")
ASR_MAX_CONCURRENCY = int(os.environ.get("ASR_MAX_CONCURRENCY", "1"))
ASR_MAX_QUEUE = int(os.environ.get("ASR_MAX_QUEUE", "8"))
ASR_PRELOAD = os.environ.get("ASR_PRELOAD", "0") not in {"0", "false", "no"}

_model = None
_sem = asyncio.Semaphore(ASR_MAX_CONCURRENCY)
_inflight = 0


def _get_model():
    """延遲載入：無 GPU 的開發機不需安裝 transformers/torch。"""
    global _model
    if _model is None:
        import torch
        from transformers import pipeline as hf_pipeline

        # DGX 實機驗證（GB10）：不指定 device 會落 CPU、一句數十秒；GPU + fp16 才夠即時。
        use_cuda = torch.cuda.is_available()
        _model = hf_pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL_ID,
            device=0 if use_cuda else -1,
            torch_dtype=torch.float16 if use_cuda else torch.float32,
        )
    return _model


def _decode_to_mono16k(audio: bytes):
    """把任意容器的音檔 bytes 解成 16k 單聲道 float32 numpy 陣列。

    HF pipeline 內建的 ffmpeg_read 是把 bytes 灌進 ffmpeg stdin(pipe) 解碼；
    m4a 的 moov atom 在檔尾時 pipe 不可 seek 會解成 partial file → 失敗
    （LINE 語音多為此類 m4a）。改成寫可 seek 的暫存檔、自行以 ffmpeg 解碼，
    輸出 raw f32le 再包成 numpy 陣列餵給 pipeline（陣列會略過 ffmpeg_read）。
    """
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                tmp_path,
                "-ac",
                "1",
                "-ar",
                str(_TARGET_SR),
                "-f",
                "f32le",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        )
    finally:
        os.unlink(tmp_path)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _transcribe(audio: bytes) -> str:
    array = _decode_to_mono16k(audio)
    result = _get_model()({"raw": array, "sampling_rate": _TARGET_SR})
    return result["text"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if ASR_PRELOAD:
        _get_model()
    yield


app = FastAPI(title="KinSun ASR (Breeze-ASR-26)", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "model_loaded": _model is not None}


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    global _inflight
    audio = await request.body()
    if _inflight >= ASR_MAX_CONCURRENCY + ASR_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="ASR 過載，請稍後再試")
    _inflight += 1
    try:
        async with _sem:
            text = await run_in_threadpool(_transcribe, audio)
    finally:
        _inflight -= 1
    return {"text": text}
