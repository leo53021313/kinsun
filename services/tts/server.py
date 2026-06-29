"""DGX 端 TTS 推論服務（台語 TTS）：提供 POST /synthesize。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/tts/requirements.txt。
啟動：uv run uvicorn services.tts.server:app --host 0.0.0.0 --port 8002

與（未來的）kinsun.speech.tts.DgxTtsClient 的契約：
- 輸入：JSON {"text": "繁體國語漢字"}。
- 輸出：原始音檔 bytes（Content-Type: audio/wav）。

狀態：骨架（placeholder）。台語 TTS 模型尚未選定，_get_model 目前明確拋出
NotImplementedError；模型就緒後只需補上載入與合成，契約不變。
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI(title="KinSun TTS (台語 TTS)")

# 模型 id 走環境變數，避免在程式碼寫死；待台語 TTS 模型選定後填入預設值。
TTS_MODEL_ID = os.environ.get("TTS_MODEL_ID", "")

_model = None


def _get_model():
    """延遲載入：無 GPU 的開發機不需安裝 TTS 引擎。"""
    global _model
    if _model is None:
        raise NotImplementedError(
            "台語 TTS 模型尚未選定；請見 services/tts/README.md 的待辦，"
            "模型就緒後在此載入並設定 TTS_MODEL_ID。"
        )
    return _model


def _synthesize(text: str) -> bytes:
    model = _get_model()
    return model(text)  # 模型就緒後回傳音檔 bytes


@app.post("/synthesize")
async def synthesize(payload: dict) -> Response:
    text = payload.get("text", "")
    audio = _synthesize(text)
    return Response(content=audio, media_type="audio/wav")
