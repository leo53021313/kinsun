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

# Gemini embedder 與 Supabase 向量庫的維度必須一致，否則向量查詢會維度不符。
# mem0 gemini embedder 預設輸出 768 維，但 supabase 向量庫預設建 1536 維 → 兩邊都明確鎖 768。
_EMBEDDING_DIMS = 768


def build_mem0_config(settings: Settings) -> dict:
    config = {
        "llm": {
            "provider": "gemini",
            "config": {"model": settings.gemini_model, "api_key": settings.gemini_api_key},
        },
        "embedder": {
            "provider": "gemini",
            "config": {
                "model": settings.longterm_embedding_model,
                "embedding_dims": _EMBEDDING_DIMS,
            },
        },
        "vector_store": {
            "provider": "supabase",
            "config": {
                "connection_string": settings.database_url,
                "collection_name": "kinsun_memories",
                "embedding_model_dims": _EMBEDDING_DIMS,
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
