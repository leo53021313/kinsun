"""集中讀取環境變數的設定。不寫死任何金鑰。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(Exception):
    """設定錯誤（缺必填環境變數等）。"""


@dataclass(frozen=True)
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    gemini_api_key: str
    gemini_model: str
    asr_backend: str
    asr_endpoint: str
    asr_timeout_seconds: float
    llm_timeout_seconds: float
    memory_db_path: str
    memory_max_turns: int
    timezone: str
    knowledge_db_path: str
    episodic_db_path: str
    episodic_top_k: int
    embedding_model: str
    consolidation_hour: int
    scheduler_tick_seconds: int


def _require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigError(f"缺少必要環境變數：{key}")
    return value


def load_settings(env: Mapping[str, str]) -> Settings:
    return Settings(
        line_channel_secret=_require(env, "LINE_CHANNEL_SECRET"),
        line_channel_access_token=_require(env, "LINE_CHANNEL_ACCESS_TOKEN"),
        gemini_api_key=_require(env, "GEMINI_API_KEY"),
        gemini_model=env.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        asr_backend=env.get("ASR_BACKEND", "mock"),
        asr_endpoint=env.get("ASR_ENDPOINT", ""),
        asr_timeout_seconds=float(env.get("ASR_TIMEOUT_SECONDS", "15")),
        llm_timeout_seconds=float(env.get("LLM_TIMEOUT_SECONDS", "30")),
        memory_db_path=env.get("MEMORY_DB_PATH", "kinsun_memory.db"),
        memory_max_turns=int(env.get("MEMORY_MAX_TURNS", "200")),
        timezone=env.get("TIMEZONE", "Asia/Taipei"),
        knowledge_db_path=env.get("KNOWLEDGE_DB_PATH", "kinsun_knowledge.db"),
        episodic_db_path=env.get("EPISODIC_DB_PATH", "kinsun_episodic.db"),
        episodic_top_k=int(env.get("EPISODIC_TOP_K", "3")),
        embedding_model=env.get("EMBEDDING_MODEL", "gemini-embedding-001"),
        consolidation_hour=int(env.get("CONSOLIDATION_HOUR", "3")),
        scheduler_tick_seconds=int(env.get("SCHEDULER_TICK_SECONDS", "60")),
    )
