"""組裝 Mem0 Memory：由設定建立 config 並建構實例。"""

from __future__ import annotations

from kinsun.config import Settings
from kinsun.longterm import provenance


def build_mem0_config(settings: Settings) -> dict:
    return {
        "llm": {
            "provider": "gemini",
            "config": {"model": settings.gemini_model, "api_key": settings.gemini_api_key},
        },
        "embedder": {
            "provider": "gemini",
            "config": {"model": settings.embedding_model},
        },
        "vector_store": {
            "provider": "supabase",
            "config": {
                "connection_string": settings.database_url,
                "collection_name": "kinsun_memories",
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
