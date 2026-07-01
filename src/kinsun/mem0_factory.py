"""組裝 Mem0 Memory：由設定建立 config 並建構實例。"""

from __future__ import annotations

from kinsun.config import Settings
from kinsun.longterm import provenance

# Gemini embedder 與 Supabase 向量庫的維度必須一致，否則向量查詢會維度不符。
# mem0 gemini embedder 預設輸出 768 維，但 supabase 向量庫預設建 1536 維 → 兩邊都明確鎖 768。
_EMBEDDING_DIMS = 768


def build_mem0_config(settings: Settings) -> dict:
    return {
        "llm": {
            "provider": "gemini",
            "config": {"model": settings.gemini_model, "api_key": settings.gemini_api_key},
        },
        "embedder": {
            "provider": "gemini",
            "config": {"model": settings.embedding_model, "embedding_dims": _EMBEDDING_DIMS},
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
        "version": "v1.1",
        "custom_instructions": provenance.CUSTOM_FACT_EXTRACTION_PROMPT,
    }


def build_mem0_memory(settings: Settings):
    from mem0 import Memory  # 延遲匯入，避免單元測試與無 key 環境載入

    return Memory.from_config(build_mem0_config(settings))
