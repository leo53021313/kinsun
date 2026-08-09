"""組裝 Mem0 Memory：由設定建立 config 並建構實例。"""

from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from pathlib import Path

from kinsun import tracing
from kinsun.config import Settings
from kinsun.memory.longterm import provenance

logger = logging.getLogger(__name__)

# embedder 與 Supabase 向量庫的維度必須一致，否則向量查詢會維度不符。mem0 的 gemini
# embedder 預設輸出 768 維、supabase 向量庫預設建 1536 維，兩邊都不能靠預設，一律明著鎖。
# ⚠️ 這兩個數字是同一個來源算出來的（`_embedding_dims`），不可各自寫死：對不上時 mem0
# 是**靜默**退化成「查不到記憶」，長輩端不會有任何錯誤，只會覺得金孫忘了她說過的話。
_GEMINI_EMBEDDING_DIMS = 768
_LOCAL_EMBEDDING_DIMS = 1024  # BAAI/bge-m3 的 dense 維度


def _embedding_dims(settings: Settings) -> int:
    return (
        _LOCAL_EMBEDDING_DIMS
        if settings.longterm_embedding_backend == "local"
        else _GEMINI_EMBEDDING_DIMS
    )


def _build_embedder_config(settings: Settings) -> dict:
    """依 backend 組 embedder：地端 BGE-M3 服務或雲端 Gemini API。

    地端走 **OpenAI 相容協定**（`services/embedding` 的 `/v1/embeddings`）而不是 mem0 的
    `huggingface` provider：後者在模組頂層 `import sentence_transformers`，會把 torch
    拉進 API 這一端，而重模型刻意只跑在 DGX 上（AGENTS.md「位置無關」）。`openai` 套件
    本來就在依賴裡，走相容協定零新增相依。

    ⚠️ 少了 endpoint 必須當場拒絕：mem0 的 OpenAIEmbedding 在 `openai_base_url` 為空時
    會退回 `https://api.openai.com/v1`（見其 `embeddings/openai.py`），於是一個設定疏漏
    會變成「把長輩的記憶送去 OpenAI」，而且因為沒有金鑰只會得到一個看似普通的 401。
    """
    dims = _embedding_dims(settings)
    if settings.longterm_embedding_backend != "local":
        return {
            "provider": "gemini",
            "config": {"model": settings.longterm_embedding_model, "embedding_dims": dims},
        }
    if not settings.longterm_embedding_endpoint:
        raise ValueError(
            "LONGTERM_EMBEDDING_BACKEND=local 需要 LONGTERM_EMBEDDING_ENDPOINT"
            "（例如 http://127.0.0.1:8003/v1）；留空會讓 mem0 改打 api.openai.com"
        )
    return {
        "provider": "openai",
        "config": {
            "model": settings.longterm_embedding_model,
            "embedding_dims": dims,
            "openai_base_url": settings.longterm_embedding_endpoint,
            # openai 套件在 api_key 為 None 時直接拋錯，故內網未設金鑰時給一個佔位字串；
            # 服務端 EMBEDDING_API_KEY 未設＝不驗（比照 ASR／TTS 的內網開發模式）。
            "api_key": settings.longterm_embedding_api_key or "not-required-on-lan",
        },
    }


def build_mem0_config(settings: Settings) -> dict:
    config = {
        "llm": {
            "provider": "gemini",
            "config": {"model": settings.gemini_model, "api_key": settings.gemini_api_key},
        },
        "embedder": _build_embedder_config(settings),
        "vector_store": {
            "provider": "supabase",
            "config": {
                "connection_string": settings.database_url,
                "collection_name": "kinsun_memories",
                # 與 embedder 同源（見 `_embedding_dims`），不可各自寫死。
                "embedding_model_dims": _embedding_dims(settings),
                "index_method": "hnsw",
                "index_measure": "cosine_distance",
            },
        },
        # 稽核檔固定進 repo 的 data/（✅ D-65 丙-13）：預設落 ~/.mem0 會隨執行機散落。
        "history_db_path": str(_history_db_path()),
        "version": "v1.1",
        "custom_instructions": provenance.CUSTOM_FACT_EXTRACTION_PROMPT,
    }
    if settings.longterm_rerank_enabled:
        # LLM reranker（✅ D-40 丁-4）：沿用 Gemini（零新依賴、中文佳）；
        # sentence_transformer 需在 API 環境裝 torch＋下載 cross-encoder，暫不採。
        config["reranker"] = {
            "provider": "llm_reranker",
            "config": {
                "provider": "gemini",
                "model": settings.gemini_model,
                "api_key": settings.gemini_api_key,
                "temperature": 0.0,
                "max_tokens": 100,
            },
        }
    return config


def _history_db_path() -> Path:
    path = Path(__file__).resolve().parents[4] / "data" / "mem0" / "history.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _disable_telemetry(environ: MutableMapping[str, str] | None = None) -> None:
    """關閉 mem0 的 PostHog 匿名遙測（長輩隱私）；只補缺、尊重使用者顯式設定。

    mem0 在 import telemetry 模組時即讀取 MEM0_TELEMETRY，故須在匯入 mem0 前設定。
    """
    env = os.environ if environ is None else environ
    env.setdefault("MEM0_TELEMETRY", "False")


def _instrument_tracing(memory):
    """把 mem0 內部三段（embedding／向量查詢／rerank）包上 Opik span。

    延遲數據要拆到「rerank 佔多少」才有辦法決定它的去留（2026-07-30 spec）。
    包在**實例屬性**上、不動 mem0 類別；`keyword_search` 不包——Supabase provider
    繼承基底的 `return None`，零網路成本。屬性缺席（mem0 升版改名）記 warning
    後原樣回傳，比照 wrap_genai：觀測絕不可壞掉記憶功能。
    """
    try:
        memory.embedding_model.embed = tracing.track(
            name="mem0_embed", capture_input=True, capture_output=False
        )(memory.embedding_model.embed)
        memory.vector_store.search = tracing.track(
            name="mem0_vector_search",
            capture_input=True,
            capture_output=False,
            ignore_arguments=["vectors"],  # 768 維查詢向量，塞進 span 只是噪音
        )(memory.vector_store.search)
        if getattr(memory, "reranker", None) is not None:
            memory.reranker.rerank = tracing.track(
                name="mem0_rerank",
                capture_input=True,
                capture_output=False,
                ignore_arguments=["documents"],  # 候選集可達數十筆記憶原文
            )(memory.reranker.rerank)
    except AttributeError:
        logger.warning("mem0 實例屬性不符（升版改名？），內部子 span 略過")
    return memory


def build_mem0_memory(settings: Settings):
    _disable_telemetry()
    from mem0 import Memory  # 延遲匯入，避免單元測試與無 key 環境載入

    return _instrument_tracing(Memory.from_config(build_mem0_config(settings)))
