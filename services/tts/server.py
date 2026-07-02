"""DGX 端 TTS 推論服務（CosyVoice 3）：提供 POST /synthesize、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/tts/requirements.txt。
啟動：uvicorn services.tts.server:app --host 0.0.0.0 --port 8002

與 kinsun.speech.tts.DgxTtsClient 的契約：
- 輸入：JSON {"text": "繁體國語漢字"}。
- 輸出：m4a（AAC）bytes、Content-Type: audio/mp4、header X-Duration-Ms。

zero-shot 聲音複製：TTS_PROMPT_WAV（參考音檔）＋ TTS_PROMPT_TEXT（其逐字稿）。
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

TTS_MODEL_ID = os.environ.get("TTS_MODEL_ID", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
TTS_PROMPT_WAV = os.environ.get("TTS_PROMPT_WAV", "")
TTS_PROMPT_TEXT = os.environ.get("TTS_PROMPT_TEXT", "")
TTS_MAX_CONCURRENCY = int(os.environ.get("TTS_MAX_CONCURRENCY", "1"))
TTS_MAX_QUEUE = int(os.environ.get("TTS_MAX_QUEUE", "8"))
TTS_PRELOAD = os.environ.get("TTS_PRELOAD", "0") not in {"0", "false", "no"}

_model = None
_prompt_16k = None
_sem = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
_inflight = 0


def _get_model():
    """延遲載入 CosyVoice 3 與參考語音；缺參考語音設定即明確報錯。"""
    global _model, _prompt_16k
    if _model is None:
        if not TTS_PROMPT_WAV or not TTS_PROMPT_TEXT:
            raise RuntimeError("需設定 TTS_PROMPT_WAV 與 TTS_PROMPT_TEXT（金孫參考語音）")
        # DGX 實機鎖定：類別名稱／建構參數依 CosyVoice repo 版本調整。
        from cosyvoice.cli.cosyvoice import CosyVoice2
        from cosyvoice.utils.file_utils import load_wav

        _model = CosyVoice2(TTS_MODEL_ID, load_jit=False, load_trt=False, fp16=True)
        _prompt_16k = load_wav(TTS_PROMPT_WAV, 16000)
    return _model


def _synthesize(text: str) -> tuple[bytes, int]:
    import torch
    import torchaudio

    model = _get_model()
    chunks = [
        out["tts_speech"]
        for out in model.inference_zero_shot(text, TTS_PROMPT_TEXT, _prompt_16k, stream=False)
    ]
    waveform = torch.cat(chunks, dim=1)  # [1, N]
    sample_rate = model.sample_rate
    duration_ms = int(waveform.shape[1] / sample_rate * 1000)

    wav_buf = io.BytesIO()
    torchaudio.save(wav_buf, waveform, sample_rate, format="wav")
    return _wav_to_m4a(wav_buf.getvalue()), duration_ms


def _wav_to_m4a(wav_bytes: bytes) -> bytes:
    """DGX 端 ffmpeg：wav → AAC/m4a（應用層跨平台、不裝 ffmpeg）。"""
    proc = subprocess.run(
        ["ffmpeg", "-f", "wav", "-i", "pipe:0", "-f", "ipod", "-c:a", "aac", "pipe:1"],
        input=wav_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout


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
