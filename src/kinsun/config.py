"""集中讀取環境變數的設定。不寫死任何金鑰。"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """設定錯誤（缺必填環境變數等）。"""


def load_dotenv(
    path: Path | None = None, *, environ: MutableMapping[str, str] | None = None
) -> None:
    """讀取 .env（若存在）填入環境變數；只補缺、不覆蓋既有變數（真實環境優先）。

    不依賴第三方套件（跨平台、無需 python-dotenv）。值中的 `=` 只切第一個。
    預設路徑為專案根目錄的 .env（相對本檔位置，與 cwd 無關）。
    """
    env = os.environ if environ is None else environ
    dotenv = Path(__file__).resolve().parents[2] / ".env" if path is None else path
    if not dotenv.is_file():
        return
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    gemini_api_key: str
    gemini_model: str
    asr_backend: str
    asr_endpoint: str
    asr_api_key: str
    asr_timeout_seconds: float
    gemini_timeout_seconds: float
    memory_max_turns: int
    timezone: str
    longterm_embedding_model: str
    longterm_consolidation_hour: int
    scheduler_tick_seconds: int
    proactive_greeting_hour: int
    proactive_inactivity_hour: int
    proactive_inactivity_days: int
    invite_ttl_hours: int
    invite_max_attempts: int
    database_url: str
    longterm_top_k: int
    binding_session_ttl_minutes: int
    medication_morning_hour: int
    medication_noon_hour: int
    medication_evening_hour: int
    medication_bedtime_hour: int
    appointment_reminder_hour: int
    rag_top_k: int
    liff_channel_id: str
    liff_timeout_seconds: float
    rich_menu_id: str
    binding_gate_enabled: bool
    tts_backend: str
    tts_endpoint: str
    tts_api_key: str
    tts_timeout_seconds: float
    tts_reply_text: bool
    supabase_url: str
    supabase_service_key: str
    audio_bucket: str
    audio_retention_days: int
    audio_upload_timeout_seconds: float
    audio_signed_url_expires_seconds: int
    audio_max_upload_bytes: int
    auth_rate_limit_max_attempts: int
    safety_confidence_high: float
    safety_confidence_mid: float
    auth_rate_limit_window_seconds: float
    asr_debug_show_transcript: bool
    line_text_input_enabled: bool
    admin_api_key: str
    admin_retention_days: int


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() not in {"0", "false", "no"}


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
        asr_api_key=env.get("ASR_API_KEY", ""),
        asr_timeout_seconds=float(env.get("ASR_TIMEOUT_SECONDS", "15")),
        gemini_timeout_seconds=float(env.get("GEMINI_TIMEOUT_SECONDS", "30")),
        memory_max_turns=int(env.get("MEMORY_MAX_TURNS", "200")),
        timezone=env.get("TIMEZONE", "Asia/Taipei"),
        longterm_embedding_model=env.get("LONGTERM_EMBEDDING_MODEL", "gemini-embedding-001"),
        longterm_consolidation_hour=int(env.get("LONGTERM_CONSOLIDATION_HOUR", "3")),
        scheduler_tick_seconds=int(env.get("SCHEDULER_TICK_SECONDS", "60")),
        proactive_greeting_hour=int(env.get("PROACTIVE_GREETING_HOUR", "8")),
        proactive_inactivity_hour=int(env.get("PROACTIVE_INACTIVITY_HOUR", "10")),
        proactive_inactivity_days=int(env.get("PROACTIVE_INACTIVITY_DAYS", "2")),
        invite_ttl_hours=int(env.get("INVITE_TTL_HOURS", "24")),
        invite_max_attempts=int(env.get("INVITE_MAX_ATTEMPTS", "5")),
        database_url=_require(env, "DATABASE_URL"),
        longterm_top_k=int(env.get("LONGTERM_TOP_K", "5")),
        binding_session_ttl_minutes=int(env.get("BINDING_SESSION_TTL_MINUTES", "10")),
        medication_morning_hour=int(env.get("MEDICATION_MORNING_HOUR", "8")),
        medication_noon_hour=int(env.get("MEDICATION_NOON_HOUR", "12")),
        medication_evening_hour=int(env.get("MEDICATION_EVENING_HOUR", "18")),
        medication_bedtime_hour=int(env.get("MEDICATION_BEDTIME_HOUR", "21")),
        appointment_reminder_hour=int(env.get("APPOINTMENT_REMINDER_HOUR", "8")),
        rag_top_k=int(env.get("RAG_TOP_K", "5")),
        liff_channel_id=env.get("LIFF_CHANNEL_ID", ""),
        liff_timeout_seconds=float(env.get("LIFF_TIMEOUT_SECONDS", "10")),
        rich_menu_id=env.get("RICH_MENU_ID", ""),
        binding_gate_enabled=_parse_bool(env.get("BINDING_GATE_ENABLED", "true")),
        tts_backend=env.get("TTS_BACKEND", "bubble"),
        tts_endpoint=env.get("TTS_ENDPOINT", ""),
        tts_api_key=env.get("TTS_API_KEY", ""),
        tts_timeout_seconds=float(env.get("TTS_TIMEOUT_SECONDS", "30")),
        tts_reply_text=_parse_bool(env.get("TTS_REPLY_TEXT", "true")),
        supabase_url=env.get("SUPABASE_URL", ""),
        supabase_service_key=env.get("SUPABASE_SERVICE_KEY", ""),
        audio_bucket=env.get("AUDIO_BUCKET", "tts-audio"),
        # 音檔本體保留天數；0＝不清理（開關保留）。2026-07-09 定案：維持 2 天清理。
        audio_retention_days=int(env.get("AUDIO_RETENTION_DAYS", "2")),
        audio_upload_timeout_seconds=float(env.get("AUDIO_UPLOAD_TIMEOUT_SECONDS", "10")),
        audio_signed_url_expires_seconds=int(env.get("AUDIO_SIGNED_URL_EXPIRES_SECONDS", "86400")),
        # 對講機單回合音檔上限（✅ D-26 env 化，原 10MB 寫死）。
        audio_max_upload_bytes=int(env.get("AUDIO_MAX_UPLOAD_BYTES", "10485760")),
        auth_rate_limit_max_attempts=int(env.get("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "10")),
        # 危急信心門檻（✅ D-41 丙-6 env 化）：數值先用現值，實測再調（會-7）；
        # 降級規則將隨 D-72 三級制重設計（己-4）。
        safety_confidence_high=float(env.get("SAFETY_CONFIDENCE_HIGH", "0.7")),
        safety_confidence_mid=float(env.get("SAFETY_CONFIDENCE_MID", "0.4")),
        auth_rate_limit_window_seconds=float(env.get("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")),
        asr_debug_show_transcript=_parse_bool(env.get("ASR_DEBUG_SHOW_TRANSCRIPT", "false")),
        # ✅ D-11（甲-4）：文字輸入為正式功能（與語音同等對待），預設開；關閉為維運逃生口。
        line_text_input_enabled=_parse_bool(env.get("LINE_TEXT_INPUT_ENABLED", "true")),
        admin_api_key=env.get("ADMIN_API_KEY", ""),
        admin_retention_days=int(env.get("ADMIN_RETENTION_DAYS", "14")),
    )
