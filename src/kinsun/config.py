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
    memory_max_turns: int
    timezone: str
    embedding_model: str
    consolidation_hour: int
    scheduler_tick_seconds: int
    greeting_hour: int
    inactivity_hour: int
    inactivity_days: int
    invite_ttl_hours: int
    invite_max_attempts: int
    database_url: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    longterm_top_k: int
    binding_session_ttl_minutes: int


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
        memory_max_turns=int(env.get("MEMORY_MAX_TURNS", "200")),
        timezone=env.get("TIMEZONE", "Asia/Taipei"),
        embedding_model=env.get("EMBEDDING_MODEL", "gemini-embedding-001"),
        consolidation_hour=int(env.get("CONSOLIDATION_HOUR", "3")),
        scheduler_tick_seconds=int(env.get("SCHEDULER_TICK_SECONDS", "60")),
        greeting_hour=int(env.get("GREETING_HOUR", "8")),
        inactivity_hour=int(env.get("INACTIVITY_HOUR", "10")),
        inactivity_days=int(env.get("INACTIVITY_DAYS", "2")),
        invite_ttl_hours=int(env.get("INVITE_TTL_HOURS", "24")),
        invite_max_attempts=int(env.get("INVITE_MAX_ATTEMPTS", "5")),
        database_url=_require(env, "DATABASE_URL"),
        neo4j_uri=_require(env, "NEO4J_URI"),
        neo4j_username=_require(env, "NEO4J_USERNAME"),
        neo4j_password=_require(env, "NEO4J_PASSWORD"),
        longterm_top_k=int(env.get("LONGTERM_TOP_K", "5")),
        binding_session_ttl_minutes=int(env.get("BINDING_SESSION_TTL_MINUTES", "10")),
    )
