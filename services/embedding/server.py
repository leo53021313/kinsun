"""DGX 端嵌入推論服務：載入 BGE-M3，提供 POST /embed、GET /healthz。

僅在 DGX（Linux + ARM64 + GPU）執行；安裝見 services/embedding/requirements.txt。
啟動：uvicorn services.embedding.server:app --host 0.0.0.0 --port 8003

與 kinsun.rag.embeddings.LocalEmbeddingModel 的契約：
- 輸入：JSON {"texts": ["…", …]}
- 輸出：JSON {"vectors": [[…1024 個 float…], …], "model": "…", "dimensions": 1024}

為什麼是 BGE-M3（2026-08-01 A/B，語料 1,113 篇真文章、2,267 chunk）：
  一般長輩口語 61 題   R@1 82.0%／MRR 0.900  ← 兩項都勝過 Gemini（78.7%／0.885）
  台語詞彙 21 題       R@1 85.7%／MRR 0.896  ← 此項 Gemini 較強（95.2%／0.968）
  建置速度             94.9 段/秒，全站 5,667 篇約 2 分鐘（Gemini 約 2.9 小時）
Gemini 免費層每支金鑰每日約 1,000 次，一輪建置就要燒掉三支；地端沒有這個限制。
台語弱勢由 retriever._SYNONYMS 的同義詞展開補（實測 R@3 90.5% → 95.2%）。
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "BAAI/bge-m3")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
EMBEDDING_MAX_CONCURRENCY = int(os.environ.get("EMBEDDING_MAX_CONCURRENCY", "1"))
EMBEDDING_MAX_QUEUE = int(os.environ.get("EMBEDDING_MAX_QUEUE", "8"))
# 單次請求最多幾段文字；超過請呼叫端自行分批。
EMBEDDING_MAX_BATCH = int(os.environ.get("EMBEDDING_MAX_BATCH", "64"))
# 單段文字的 token 上限。BGE-M3 支援 8192，但衛教 chunk 約 500 字，1024 綽綽有餘，
# 且上限拉高會讓最長那段拖慢整批（padding 到最長）。
EMBEDDING_MAX_TOKENS = int(os.environ.get("EMBEDDING_MAX_TOKENS", "1024"))
# 共用金鑰：設定後驗 X-Api-Key；未設＝內網開發模式不驗（比照 ASR／TTS）。
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_PRELOAD = os.environ.get("EMBEDDING_PRELOAD", "0") not in {"0", "false", "no"}

_model = None
_tokenizer = None
_sem = asyncio.Semaphore(EMBEDDING_MAX_CONCURRENCY)
_inflight = 0


def _get_model():
    """延遲載入：無 GPU 的開發機不需安裝 transformers/torch。"""
    global _model, _tokenizer
    if _model is None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        # padding 方向必須配合 pooling：BGE-M3 的 dense 向量取 CLS（位置 0），
        # 靠左 padding 會讓位置 0 變成 padding token。2026-08-01 實測誤設成 left
        # 時 R@1 從 98.4% 掉到 39.3%，數字看起來只是「模型比較差」，很難察覺。
        _tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL_ID, padding_side="right")
        use_cuda = torch.cuda.is_available()
        _model = (
            AutoModel.from_pretrained(
                EMBEDDING_MODEL_ID,
                dtype=torch.float16 if use_cuda else torch.float32,
            )
            .to("cuda" if use_cuda else "cpu")
            .eval()
        )
        logger.info("嵌入模型已載入：%s（cuda=%s）", EMBEDDING_MODEL_ID, use_cuda)
    return _model, _tokenizer


def _embed(texts: list[str]) -> list[list[float]]:
    import torch

    model, tokenizer = _get_model()
    device = next(model.parameters()).device
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=EMBEDDING_MAX_TOKENS,
        return_tensors="pt",
    ).to(device)
    with torch.no_grad():
        hidden = model(**encoded).last_hidden_state
    pooled = hidden[:, 0].float()  # CLS pooling（BGE-M3 官方 dense 取法）
    normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return normalized.cpu().tolist()


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)


async def lifespan(_app: FastAPI):
    if EMBEDDING_PRELOAD:
        _get_model()
    yield


app = FastAPI(title="KinSun Embedding (BGE-M3)", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "model": EMBEDDING_MODEL_ID,
        "dimensions": EMBEDDING_DIMENSIONS,
        "model_loaded": _model is not None,
    }


def _require_api_key(request: Request) -> None:
    if not EMBEDDING_API_KEY:
        return
    if not hmac.compare_digest(request.headers.get("x-api-key", ""), EMBEDDING_API_KEY):
        raise HTTPException(status_code=401, detail="invalid_api_key")


@app.post("/embed")
async def embed(payload: EmbedRequest, request: Request) -> dict:
    global _inflight
    _require_api_key(request)
    if len(payload.texts) > EMBEDDING_MAX_BATCH:
        raise HTTPException(status_code=413, detail="batch_too_large")
    if any(not text.strip() for text in payload.texts):
        raise HTTPException(status_code=400, detail="empty_text")
    if _inflight >= EMBEDDING_MAX_CONCURRENCY + EMBEDDING_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="overloaded")
    _inflight += 1
    try:
        async with _sem:
            vectors = await run_in_threadpool(_embed, payload.texts)
    finally:
        _inflight -= 1
    return {
        "vectors": vectors,
        "model": EMBEDDING_MODEL_ID,
        "dimensions": len(vectors[0]) if vectors else EMBEDDING_DIMENSIONS,
    }
