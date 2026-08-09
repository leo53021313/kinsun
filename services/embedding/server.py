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
    """驗共用金鑰；未設＝內網開發模式不驗（比照 ASR／TTS）。

    收兩種標頭：`X-Api-Key` 是本服務原生的作法（RAG 的 `LocalEmbeddingModel` 用它），
    `Authorization: Bearer` 則是 OpenAI 相容端點的必要條件——openai 套件只會把金鑰
    放進 Bearer，不會送 X-Api-Key，而 mem0 走 `provider="openai"` 打 `/v1/embeddings`
    時用的正是那個套件。
    """
    if not EMBEDDING_API_KEY:
        return
    supplied = request.headers.get("x-api-key", "")
    if not supplied:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = token.strip()
    if not hmac.compare_digest(supplied, EMBEDDING_API_KEY):
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


# OpenAI `/v1/embeddings` 的兩種編碼。⚠️ **base64 是 openai 套件的預設值**，不是選配：
# 新版 SDK 為了省傳輸量，未指定 encoding_format 時一律送 base64，再自己解回 float。
# 只支援 float 的話，mem0 走 openai provider 打過來的第一個請求就會拿到 400——而這
# 在手工組 JSON 的測試裡完全看不出來（2026-08-07 用真的 openai 套件實測才發現）。
_ENCODINGS = frozenset({"float", "base64"})


def _encode_base64(vector: list[float]) -> str:
    """比照 OpenAI：float32 小端序原始位元組再 base64。

    dtype 必須是 float32——SDK 端固定以 `np.frombuffer(..., dtype="float32")` 解碼，
    給 float64 會讓維度整整多一倍，而且解出來的數值全是亂的。
    """
    import base64
    import struct

    return base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode("ascii")


class OpenAIEmbeddingRequest(BaseModel):
    """OpenAI `POST /v1/embeddings` 的請求子集（只收本服務用得到的欄位）。"""

    input: str | list[str]
    model: str | None = None  # 呼叫端指定的名字僅供辨識；本服務永遠是 EMBEDDING_MODEL_ID
    dimensions: int | None = None
    encoding_format: str | None = None


@app.post("/v1/embeddings")
async def openai_embeddings(payload: OpenAIEmbeddingRequest, request: Request) -> dict:
    """OpenAI 相容端點，供 mem0 的長期記憶檢索使用（`provider="openai"`＋`openai_base_url`）。

    為什麼另開一個端點而不是改 `/embed`：`/embed` 是 RAG 收錄與檢索的既有契約
    （`kinsun.rag.embeddings.LocalEmbeddingModel`），不該為了第二個呼叫端變形。兩個
    端點共用同一顆已載入的模型與同一道併發閘，只是外皮不同。

    為什麼不用 mem0 的 `huggingface` provider：它在模組頂層 `import sentence_transformers`
    （連帶拉進 torch），而 API 那一端刻意不裝這些重相依；`openai` 套件本來就在依賴裡，
    走相容協定零新增相依。

    ⚠️ `dimensions` 必須明著拒絕不合的值：mem0 設了 `embedding_dims` 就會把它傳下來
    （見 mem0 `embeddings/openai.py`）。BGE-M3 的 dense 維度固定 1024，收到 768 這種
    要求若悄悄回 1024，呼叫端會以為截斷成功、把 1024 維寫進 768 維的向量庫才爆，
    而那時的錯誤訊息離根因已經很遠。
    """
    global _inflight
    _require_api_key(request)
    if payload.encoding_format is not None and payload.encoding_format not in _ENCODINGS:
        raise HTTPException(status_code=400, detail="unsupported_encoding_format")
    texts = [payload.input] if isinstance(payload.input, str) else list(payload.input)
    if not texts:
        raise HTTPException(status_code=422, detail="empty_input")
    if len(texts) > EMBEDDING_MAX_BATCH:
        raise HTTPException(status_code=413, detail="batch_too_large")
    if any(not text.strip() for text in texts):
        raise HTTPException(status_code=400, detail="empty_text")
    if payload.dimensions is not None and payload.dimensions != EMBEDDING_DIMENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_dimensions")
    if _inflight >= EMBEDDING_MAX_CONCURRENCY + EMBEDDING_MAX_QUEUE:
        raise HTTPException(status_code=503, detail="overloaded")
    _inflight += 1
    try:
        async with _sem:
            vectors = await run_in_threadpool(_embed, texts)
    finally:
        _inflight -= 1
    as_base64 = payload.encoding_format == "base64"
    return {
        "object": "list",
        # index 必須忠實對應輸入順序：mem0 的 embed_batch 依它重新排序（見其 openai.py），
        # 順序錯置會讓記憶與向量張冠李戴，而那看起來完全正常。
        "data": [
            {
                "object": "embedding",
                "index": index,
                "embedding": _encode_base64(vector) if as_base64 else vector,
            }
            for index, vector in enumerate(vectors)
        ],
        "model": EMBEDDING_MODEL_ID,
        # 本服務不計費，token 數僅為滿足 OpenAI 協定的必填欄位；不假裝算得準。
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }
