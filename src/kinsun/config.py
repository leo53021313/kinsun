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
    gemini_model_safety: str
    gemini_model_summary: str
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
    # 每進程連線池上限（✅ 庚-26／A-55）：總量公式見 .env.example 與 14 部署文檔。
    database_pool_max_size: int
    longterm_top_k: int
    longterm_health_top_k: int
    longterm_rerank_enabled: bool
    binding_session_ttl_minutes: int
    medication_morning_hour: int
    medication_noon_hour: int
    medication_evening_hour: int
    medication_bedtime_hour: int
    appointment_reminder_hour: int
    rag_top_k: int
    tavily_api_key: str
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
    safety_confidence_mid: float
    auth_rate_limit_window_seconds: float
    asr_debug_show_transcript: bool
    line_text_input_enabled: bool
    admin_api_key: str
    admin_retention_days: int
    internal_testing_enabled: bool
    reflection_enabled: bool
    reflection_lookback_days: int
    reflection_min_observed_days: int
    reflection_max_strategies: int
    reflection_response_window_minutes: int


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() not in {"0", "false", "no"}


def _require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigError(f"缺少必要環境變數：{key}")
    return value


def _require_positive_int(env: Mapping[str, str], key: str, default: str) -> int:
    """讀取整數設定並確保 ≥ 1；0 或負數會讓對應功能靜默失效或行為未定義。"""
    value = int(env.get(key, default))
    if value < 1:
        raise ConfigError(f"{key}（{value}）必須大於或等於 1。")
    return value


def load_settings(env: Mapping[str, str]) -> Settings:
    # 反思設定的不變量在啟動時就檢查（fail-fast）：反思是夜間批次，設定矛盾若留到凌晨的
    # job 才浮現，只會表現成「今晚沒找到模式」——沒有錯誤、沒有告警，可能潛伏數週。
    reflection_lookback_days = _require_positive_int(env, "REFLECTION_LOOKBACK_DAYS", "7")
    reflection_min_observed_days = _require_positive_int(env, "REFLECTION_MIN_OBSERVED_DAYS", "3")
    if reflection_min_observed_days > reflection_lookback_days:
        raise ConfigError(
            f"REFLECTION_MIN_OBSERVED_DAYS（{reflection_min_observed_days}）不得大於 "
            f"REFLECTION_LOOKBACK_DAYS（{reflection_lookback_days}）："
            "證據門檻超出回顧視野時，沒有守則能通過門檻，反思會每晚空轉卻不報錯。"
        )
    return Settings(
        line_channel_secret=_require(env, "LINE_CHANNEL_SECRET"),
        line_channel_access_token=_require(env, "LINE_CHANNEL_ACCESS_TOKEN"),
        gemini_api_key=_require(env, "GEMINI_API_KEY"),
        gemini_model=env.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        # 按用途配模型（✅ D-16 丁-5）：未設＝沿用 GEMINI_MODEL；升級時危急分級優先換強模型。
        gemini_model_safety=env.get("GEMINI_MODEL_SAFETY", "")
        or env.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        gemini_model_summary=env.get("GEMINI_MODEL_SUMMARY", "")
        or env.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        asr_backend=env.get("ASR_BACKEND", "mock"),
        asr_endpoint=env.get("ASR_ENDPOINT", ""),
        asr_api_key=env.get("ASR_API_KEY", ""),
        asr_timeout_seconds=float(env.get("ASR_TIMEOUT_SECONDS", "15")),
        gemini_timeout_seconds=float(env.get("GEMINI_TIMEOUT_SECONDS", "30")),
        memory_max_turns=int(env.get("MEMORY_MAX_TURNS", "200")),
        timezone=env.get("TIMEZONE", "Asia/Taipei"),
        longterm_embedding_model=env.get("LONGTERM_EMBEDDING_MODEL", "gemini-embedding-001"),
        longterm_consolidation_hour=int(env.get("LONGTERM_CONSOLIDATION_HOUR", "0")),
        scheduler_tick_seconds=int(env.get("SCHEDULER_TICK_SECONDS", "60")),
        proactive_greeting_hour=int(env.get("PROACTIVE_GREETING_HOUR", "8")),
        proactive_inactivity_hour=int(env.get("PROACTIVE_INACTIVITY_HOUR", "10")),
        proactive_inactivity_days=int(env.get("PROACTIVE_INACTIVITY_DAYS", "2")),
        invite_ttl_hours=int(env.get("INVITE_TTL_HOURS", "24")),
        invite_max_attempts=int(env.get("INVITE_MAX_ATTEMPTS", "5")),
        database_url=_require(env, "DATABASE_URL"),
        database_pool_max_size=int(env.get("DATABASE_POOL_MAX_SIZE", "5")),
        longterm_top_k=int(env.get("LONGTERM_TOP_K", "5")),
        longterm_health_top_k=int(env.get("LONGTERM_HEALTH_TOP_K", "3")),
        # 記憶檢索重排（✅ D-40 丁-4）：LLM reranker，決議預設開；額度吃緊時可關。
        longterm_rerank_enabled=_parse_bool(env.get("LONGTERM_RERANK_ENABLED", "true")),
        binding_session_ttl_minutes=int(env.get("BINDING_SESSION_TTL_MINUTES", "10")),
        medication_morning_hour=int(env.get("MEDICATION_MORNING_HOUR", "8")),
        medication_noon_hour=int(env.get("MEDICATION_NOON_HOUR", "12")),
        medication_evening_hour=int(env.get("MEDICATION_EVENING_HOUR", "18")),
        medication_bedtime_hour=int(env.get("MEDICATION_BEDTIME_HOUR", "21")),
        appointment_reminder_hour=int(env.get("APPOINTMENT_REMINDER_HOUR", "8")),
        rag_top_k=int(env.get("RAG_TOP_K", "5")),
        # 上網查證金鑰（spec 2026-07-14）：留空＝不註冊 web_search 工具（優雅降級）。
        tavily_api_key=env.get("TAVILY_API_KEY", ""),
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
        safety_confidence_mid=float(env.get("SAFETY_CONFIDENCE_MID", "0.4")),
        auth_rate_limit_window_seconds=float(env.get("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300")),
        asr_debug_show_transcript=_parse_bool(env.get("ASR_DEBUG_SHOW_TRANSCRIPT", "false")),
        # ✅ D-11（甲-4）：文字輸入為正式功能（與語音同等對待），預設開；關閉為維運逃生口。
        line_text_input_enabled=_parse_bool(env.get("LINE_TEXT_INPUT_ENABLED", "true")),
        admin_api_key=env.get("ADMIN_API_KEY", ""),
        admin_retention_days=int(env.get("ADMIN_RETENTION_DAYS", "14")),
        # 內測模式總開關（spec 2026-07-12）：App 切換身分＋後台手動觸發；正式環境務必 false。
        internal_testing_enabled=_parse_bool(env.get("INTERNAL_TESTING_ENABLED", "false")),
        # 每晚反思（spec 2026-07-14）：預設開——反思是自動主線行為，此旗標為緊急關閉開關。
        reflection_enabled=_parse_bool(env.get("REFLECTION_ENABLED", "true")),
        # 回顧天數：證據門檻要求「跨多天重複出現」，反思就必須看得到多天（上方已驗證）。
        reflection_lookback_days=reflection_lookback_days,
        # 證據門檻：一條守則至少要在幾天中被觀察到才成立（擋掉單日噪音）。
        reflection_min_observed_days=reflection_min_observed_days,
        # 守則上限＝注入 prompt 的條數上限；滿了必須指定取代對象。
        reflection_max_strategies=_require_positive_int(env, "REFLECTION_MAX_STRATEGIES", "15"),
        # 提醒發出後多久內長輩有發言即算「已回應」。
        reflection_response_window_minutes=_require_positive_int(
            env, "REFLECTION_RESPONSE_WINDOW_MINUTES", "60"
        ),
    )
