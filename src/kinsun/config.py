"""集中讀取環境變數的設定。不寫死任何金鑰。"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

from croniter import croniter

# 只從無相依的常數模組取用，不要改成 import greeting_time：那會沿著
# greeting_time → memory.shortterm → db 把 psycopg 拖進這個全庫最低層的模組，
# 並讓任何「db／llm 想讀設定」的合理需求變成硬循環匯入。回歸測試見
# tests/test_config.py::test_importing_config_does_not_pull_in_the_database_driver。
from kinsun.proactive.constants import SLOT_MINUTES


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
    location_stale_after_hours: int
    tavily_api_key: str
    rag_content_policy: str
    rag_embedding_model: str
    rag_refresh_enabled: bool
    rag_refresh_cron: str
    rag_audit_retention_days: int
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
    reflection_max_turns: int
    proactive_greeting_adaptive_enabled: bool
    proactive_greeting_lookback_days: int
    proactive_greeting_min_sample_days: int
    proactive_greeting_earliest_hour: int
    proactive_greeting_latest_hour: int
    proactive_greeting_max_shift_minutes: int
    proactive_greeting_lag_tolerance_minutes: int


@dataclass(frozen=True)
class RagWorkerSettings:
    """獨立 RAG Worker 所需設定，不綁 LINE、語音、LIFF 或主動關懷。"""

    database_url: str
    database_pool_max_size: int
    gemini_api_key: str
    timezone: str
    scheduler_tick_seconds: int
    rag_content_policy: str
    rag_embedding_model: str
    rag_refresh_enabled: bool
    rag_refresh_cron: str
    rag_audit_retention_days: int


# 讀成 False 的值。`off` 與空值（含純空白）必須在列：布林旗標裡有緊急關閉開關
# （`REFLECTION_ENABLED` 之於每晚反思——自動生效、無人審、每晚自動跑），把 `off` 或
# `REFLECTION_ENABLED=`（值被刪掉）讀成 True，等於在半夜要關功能的人面前給他一個
# 「已關閉」的錯覺，而它照跑。
#
# 刻意維持黑名單、不改成白名單（只列真值）：白名單會把所有未列舉的值從 True 翻成
# False，靜默改掉 rerank 等旗標的既有行為。這裡只擴大「假」的集合，修正目前被誤讀成
# True 的值，不動任何一個現行正確的語意。
_FALSE_VALUES = frozenset({"", "0", "false", "no", "n", "off"})


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() not in _FALSE_VALUES


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


def _require_hour(env: Mapping[str, str], key: str, default: str) -> int:
    """讀取鐘點設定並確保落在 0..23。

    刻意不沿用 `_require_positive_int`：它擋掉 `< 1`，會誤擋合法的 0 點。兩者是不同的
    關切——那個管「數量至少要有 1」，這個管「鐘點必須是真的鐘點」。
    """
    value = int(env.get(key, default))
    if not 0 <= value <= 23:
        raise ConfigError(f"{key}（{value}）必須介於 0 到 23 之間。")
    return value


def load_rag_worker_settings(env: Mapping[str, str]) -> RagWorkerSettings:
    """只載入 RAG 週更程序實際依賴，避免被其他 channel 的金鑰阻擋。"""
    return RagWorkerSettings(
        database_url=_require(env, "DATABASE_URL"),
        database_pool_max_size=_positive_int(
            env.get("DATABASE_POOL_MAX_SIZE", "5"),
            "DATABASE_POOL_MAX_SIZE",
        ),
        gemini_api_key=_require(env, "GEMINI_API_KEY"),
        timezone=env.get("TIMEZONE", "Asia/Taipei"),
        scheduler_tick_seconds=_positive_int(
            env.get("SCHEDULER_TICK_SECONDS", "60"),
            "SCHEDULER_TICK_SECONDS",
        ),
        rag_content_policy=_rag_content_policy(env.get("RAG_CONTENT_POLICY", "allowed_only")),
        rag_embedding_model=env.get("RAG_EMBEDDING_MODEL", "") or "gemini-embedding-001",
        rag_refresh_enabled=_parse_bool(env.get("RAG_REFRESH_ENABLED", "false")),
        rag_refresh_cron=_rag_refresh_cron(env.get("RAG_REFRESH_CRON", "") or "0 3 * * 0"),
        rag_audit_retention_days=_positive_int(
            env.get("RAG_AUDIT_RETENTION_DAYS", "90"),
            "RAG_AUDIT_RETENTION_DAYS",
        ),
    )


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
    # 自適應問候的護欄同樣在啟動時檢查（fail-fast）：這機制會自動改變系統對長輩的行為
    # 時間，護欄比演算法重要——算錯了沒有護欄就是半夜三點吵醒人。以下兩個不變量的失效
    # 都是靜默的，留到夜裡的 job 才浮現時，看不出任何異常。
    proactive_greeting_lookback_days = _require_positive_int(
        env, "PROACTIVE_GREETING_LOOKBACK_DAYS", "14"
    )
    proactive_greeting_min_sample_days = _require_positive_int(
        env, "PROACTIVE_GREETING_MIN_SAMPLE_DAYS", "5"
    )
    # 範圍先驗（順序檢查涵蓋不到）：順序只約束兩者的關係，不約束各自的範圍——`EARLIEST=-5`
    # 配 `LATEST=99` 照樣滿足 -5 < 99。這是四道護欄裡唯一負責把算出的時間夾住的一道，區間
    # 一旦變成 [-5, 99] 就等於沒有夾取，而且是靜默的：不報錯，系統看起來還在自適應。
    proactive_greeting_earliest_hour = _require_hour(env, "PROACTIVE_GREETING_EARLIEST_HOUR", "6")
    proactive_greeting_latest_hour = _require_hour(env, "PROACTIVE_GREETING_LATEST_HOUR", "11")
    # 上下限顛倒＝夾取區間為空，問候時間會被夾成一個荒謬的值；啟動即失敗，不要等到夜裡才發現。
    if proactive_greeting_earliest_hour >= proactive_greeting_latest_hour:
        raise ConfigError(
            f"PROACTIVE_GREETING_EARLIEST_HOUR（{proactive_greeting_earliest_hour}）"
            f"必須小於 PROACTIVE_GREETING_LATEST_HOUR（{proactive_greeting_latest_hour}）。"
        )
    # 基準問候時間本身也是鐘點，同樣要驗證：它是自適應關閉時全體長輩的問候時間，也是
    # 自適應開啟時的起算點。裸的 int() 會讓 25 點、-3 點靜默通過。
    proactive_greeting_hour = _require_hour(env, "PROACTIVE_GREETING_HOUR", "8")
    # 基準值落在自己的上下限之外＝自相矛盾的設定。夜間批次的護軌會把它夾回界內（縱深
    # 防禦，刻意保留），但那是靜默的補救：維運只會看到「設了 5 點、系統卻在 6 點問候」，
    # 找不出原因。矛盾的設定要在啟動時就講清楚，而不是讓下游默默替它圓場。
    if not (
        proactive_greeting_earliest_hour
        <= proactive_greeting_hour
        <= proactive_greeting_latest_hour
    ):
        raise ConfigError(
            f"PROACTIVE_GREETING_HOUR（{proactive_greeting_hour}）必須介於 "
            f"PROACTIVE_GREETING_EARLIEST_HOUR（{proactive_greeting_earliest_hour}）與 "
            f"PROACTIVE_GREETING_LATEST_HOUR（{proactive_greeting_latest_hour}）之間："
            "基準問候時間落在自己的護軌外，等於要求系統在被自己禁止的時間問候。"
        )
    # 往前的死區（同時是兩個方向共用的步伐大小）與往後的容忍度。
    proactive_greeting_max_shift_minutes = _require_positive_int(
        env, "PROACTIVE_GREETING_MAX_SHIFT_MINUTES", "30"
    )
    # 步伐必須是掃描間隔的正倍數：步伐算完會經 greeting_time._align 對齊到半點（問候 job
    # 每半小時掃描），對齊會把非倍數的步伐**吃掉或放大**，兩種誤設都是靜默的——
    #   * ≤ 15：每一步都被捨回原點 → 問候時間永遠不動，機制看起來在跑卻完全癱瘓。
    #   * 非倍數（如 45）：對齊往上進位 → 實際位移超過宣稱的上限（45 → 位移 60 分）。
    # SLOT_MINUTES 取自 greeting_time（唯一真實來源），不在此寫死 30——兩份真相會漂移。
    if proactive_greeting_max_shift_minutes % SLOT_MINUTES != 0:
        raise ConfigError(
            f"PROACTIVE_GREETING_MAX_SHIFT_MINUTES（{proactive_greeting_max_shift_minutes}）"
            f"必須是問候掃描間隔 {SLOT_MINUTES} 分的正倍數（如 {SLOT_MINUTES}、"
            f"{SLOT_MINUTES * 2}）："
            f"問候時間一律對齊半點，非倍數的步伐會被對齊吃掉或放大，且不會報錯——"
            f"小於 {SLOT_MINUTES} 會被捨回原點（問候時間永遠不動，自適應等同癱瘓）；"
            f"大於 {SLOT_MINUTES} 但非倍數會往上進位（實際位移超過你設定的上限）。"
        )
    proactive_greeting_lag_tolerance_minutes = _require_positive_int(
        env, "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES", "60"
    )
    # 往後的容忍度比往前的死區還緊＝設計意圖被反轉。容忍度之所以存在，是因為「她在問候
    # 之後才有動靜」是模糊訊號（分不出「還沒醒」與「只是慢慢看手機」），往後調必須比往前
    # 調保守；反過來設，往前調就變得比往後調保守，機制照跑、不報錯，但方向錯了。
    if proactive_greeting_lag_tolerance_minutes < proactive_greeting_max_shift_minutes:
        raise ConfigError(
            f"PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES（{proactive_greeting_lag_tolerance_minutes}）"
            f"不得小於 PROACTIVE_GREETING_MAX_SHIFT_MINUTES"
            f"（{proactive_greeting_max_shift_minutes}）："
            "往後的容忍度比往前的死區還鬆是刻意的設計（問候後才有動靜是模糊訊號），"
            "反過來設會讓往前調比往後調保守，與設計意圖相反。"
        )
    # 樣本門檻超出回顧視野＝永遠湊不到樣本，問候時間永遠不會調整，且不會報錯。
    if proactive_greeting_min_sample_days > proactive_greeting_lookback_days:
        raise ConfigError(
            f"PROACTIVE_GREETING_MIN_SAMPLE_DAYS（{proactive_greeting_min_sample_days}）不得大於 "
            f"PROACTIVE_GREETING_LOOKBACK_DAYS（{proactive_greeting_lookback_days}）："
            "樣本門檻超出回顧視野時，永遠湊不到足夠樣本，問候時間永遠不會調整卻不報錯。"
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
        # 基準問候時間（上方已驗證為真的鐘點，且落在自適應的上下限內）。
        proactive_greeting_hour=proactive_greeting_hour,
        proactive_inactivity_hour=int(env.get("PROACTIVE_INACTIVITY_HOUR", "10")),
        proactive_inactivity_days=int(env.get("PROACTIVE_INACTIVITY_DAYS", "2")),
        # 自適應問候時間（spec 2026-07-16）：預設開；關閉則全體回退 PROACTIVE_GREETING_HOUR。
        proactive_greeting_adaptive_enabled=_parse_bool(
            env.get("PROACTIVE_GREETING_ADAPTIVE_ENABLED", "true")
        ),
        # 回顧幾天的活躍紀錄來推算問候時間（上方已驗證）。
        proactive_greeting_lookback_days=proactive_greeting_lookback_days,
        # 樣本門檻：至少幾天有活躍才調整；不足則不動（上方已驗證 ≤ 回顧視野）。
        proactive_greeting_min_sample_days=proactive_greeting_min_sample_days,
        # 問候時間上下限：統計再怎麼算都夾在這個區間內（上方已驗證順序）。
        proactive_greeting_earliest_hour=proactive_greeting_earliest_hour,
        proactive_greeting_latest_hour=proactive_greeting_latest_hour,
        # 單次最大調整幅度（分鐘，兩個方向共用），同時是往「前」調的死區門檻（上方已驗證）。
        proactive_greeting_max_shift_minutes=proactive_greeting_max_shift_minutes,
        # 往「後」調的死區門檻（上方已驗證 ≥ MAX_SHIFT）：她在問候後多久內有動靜都算正常。
        proactive_greeting_lag_tolerance_minutes=proactive_greeting_lag_tolerance_minutes,
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
        # 位置超過幾小時就不再採信、不注入 prompt（spec 2026-07-17）。
        # 只影響主動問候路徑——長輩講話時才抓位置，對話中的位置必然是幾秒前的。
        location_stale_after_hours=_require_positive_int(env, "LOCATION_STALE_AFTER_HOURS", "2"),
        # 上網查證金鑰（spec 2026-07-14）：留空＝不註冊 web_search 工具（優雅降級）。
        tavily_api_key=env.get("TAVILY_API_KEY", ""),
        rag_content_policy=_rag_content_policy(env.get("RAG_CONTENT_POLICY", "allowed_only")),
        rag_embedding_model=env.get("RAG_EMBEDDING_MODEL", "") or "gemini-embedding-001",
        rag_refresh_enabled=_parse_bool(env.get("RAG_REFRESH_ENABLED", "false")),
        rag_refresh_cron=_rag_refresh_cron(env.get("RAG_REFRESH_CRON", "") or "0 3 * * 0"),
        rag_audit_retention_days=_positive_int(
            env.get("RAG_AUDIT_RETENTION_DAYS", "90"),
            "RAG_AUDIT_RETENTION_DAYS",
        ),
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
        # 反思單次讀取的輪數上限（與聊天上下文的 MEMORY_MAX_TURNS 是兩個不同的窗）。
        # 600 ＝ 七天 × 每天約 85 輪：涵蓋絕大多數長輩的整個回顧窗，token 成本仍可控
        # （約 3～6 萬 token）。超量時丟的是最舊的輪次，並記 warning。
        reflection_max_turns=_require_positive_int(env, "REFLECTION_MAX_TURNS", "600"),
    )


def _rag_content_policy(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"allowed_only", "classroom_demo"}:
        raise ConfigError("RAG_CONTENT_POLICY 必須為 allowed_only 或 classroom_demo。")
    return normalized


def _rag_refresh_cron(value: str) -> str:
    normalized = value.strip()
    if not croniter.is_valid(normalized):
        raise ConfigError("RAG_REFRESH_CRON 不是有效的 cron 表達式。")
    return normalized


def _positive_int(value: str, key: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} 必須是正整數。") from exc
    if parsed <= 0:
        raise ConfigError(f"{key} 必須是正整數。")
    return parsed
