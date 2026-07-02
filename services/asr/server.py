"""DGX 端 ASR 推論服務：載入 Breeze-ASR-26，提供 POST /transcribe。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/asr/requirements.txt。
啟動：uv run uvicorn services.asr.server:app --host 0.0.0.0 --port 8001

與 kinsun.speech.asr.DgxAsrClient 的契約：
- 輸入：HTTP body 為原始音檔 bytes（Content-Type 由呼叫端帶入）。
- 輸出：JSON {"text": "繁體國語漢字"}。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request

app = FastAPI(title="KinSun ASR (Breeze-ASR-26)")

# 模型 id 走環境變數，避免在程式碼寫死；預設值需於 DGX 上以實機驗證。
ASR_MODEL_ID = os.environ.get("ASR_MODEL_ID", "MediaTek-Research/Breeze-ASR-26")

_model = None


def _get_model():
    """延遲載入：無 GPU 的開發機不需安裝 transformers/torch。"""
    global _model
    if _model is None:
        import torch
        from transformers import pipeline as hf_pipeline

        # DGX 實機驗證（2026-07-02，GB10）：不指定 device 會落在 CPU，
        # whisper-large 級模型一句要數十秒；GPU + fp16 才夠即時。
        use_cuda = torch.cuda.is_available()
        _model = hf_pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL_ID,
            device=0 if use_cuda else -1,
            torch_dtype=torch.float16 if use_cuda else torch.float32,
        )
    return _model


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    audio = await request.body()
    model = _get_model()
    result = model(audio)
    return {"text": result["text"]}
