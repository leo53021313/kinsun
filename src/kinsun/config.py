"""集中讀取環境變數的設定。不寫死任何金鑰。

以 pydantic-settings 承載欄位宣告、型別強制與凍結（`frozen=True`）；環境變數的來源
走自訂 `_MappingSettingsSource`，讓 `load_settings(env)` 能吃「注入的任意 mapping」
（production 傳 `os.environ`、測試傳 dict），且測試不會意外漏讀真實 `os.environ`。

刻意保留的行為（皆有回歸測試）：
* bool 走黑名單解析（`off`／空值／純空白＝False，其餘皆 True），非 pydantic 原生 bool。
* 驗證失敗一律拋 `ConfigError`（非 pydantic `ValidationError`），訊息自解釋含大寫鍵名與值。
* 跨欄位 fail-fast 護欄（反思、自適應問候）在載入當下就攔下矛盾設定。
* 模型分用途 fallback（safety／summary 未設沿用主模型）、rag 空值回預設。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any

from croniter import croniter
from pydantic import BeforeValidator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

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


# 讀成 False 的值。`off` 與空值（含純空白）必須在列：布林旗標裡有緊急關閉開關
# （`REFLECTION_ENABLED` 之於每晚反思——自動生效、無人審、每晚自動跑），把 `off` 或
# `REFLECTION_ENABLED=`（值被刪掉）讀成 True，等於在半夜要關功能的人面前給他一個
# 「已關閉」的錯覺，而它照跑。
#
# 刻意維持黑名單、不改成白名單（只列真值）：白名單會把所有未列舉的值從 True 翻成
# False，靜默改掉 rerank 等旗標的既有行為。這裡只擴大「假」的集合，修正目前被誤讀成
# True 的值，不動任何一個現行正確的語意。
_FALSE_VALUES = frozenset({"", "0", "false", "no", "n", "off"})


def _parse_bool(raw: Any) -> bool:
    return str(raw).strip().lower() not in _FALSE_VALUES


# bool 欄位一律用此標註，重現黑名單語意（pydantic 原生 bool 會拒收 `y`／`on`／任意字串）。
Bool = Annotated[bool, BeforeValidator(_parse_bool)]


def _at_least_one(key: str):
    """回傳一個 before 驗證器：整數且 ≥ 1，否則拋 ConfigError（含鍵名與值）。"""

    def _validate(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key}（{value}）必須大於或等於 1。") from exc
        if parsed < 1:
            raise ConfigError(f"{key}（{value}）必須大於或等於 1。")
        return parsed

    return _validate


def _positive(key: str):
    """回傳一個 before 驗證器：整數且 > 0，否則拋 ConfigError（含鍵名）。"""

    def _validate(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key} 必須是正整數。") from exc
        if parsed <= 0:
            raise ConfigError(f"{key} 必須是正整數。")
        return parsed

    return _validate


def _hour(key: str):
    """回傳一個 before 驗證器：鐘點落在 0..23，否則拋 ConfigError（含鍵名與值）。

    刻意不沿用 `_at_least_one`：那擋掉 `< 1`，會誤擋合法的 0 點。兩者是不同的關切——
    那個管「數量至少要有 1」，這個管「鐘點必須是真的鐘點」。
    """

    def _validate(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key}（{value}）必須介於 0 到 23 之間。") from exc
        if not 0 <= parsed <= 23:
            raise ConfigError(f"{key}（{value}）必須介於 0 到 23 之間。")
        return parsed

    return _validate


def _content_policy(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized not in {"allowed_only", "classroom_demo"}:
        raise ConfigError("RAG_CONTENT_POLICY 必須為 allowed_only 或 classroom_demo。")
    return normalized


def _refresh_cron(value: Any) -> str:
    normalized = str(value).strip() or "0 3 * * 0"
    if not croniter.is_valid(normalized):
        raise ConfigError("RAG_REFRESH_CRON 不是有效的 cron 表達式。")
    return normalized


def _embedding_model(value: Any) -> str:
    # 空值＝回預設模型（與原 `env.get(...) or "gemini-embedding-001"` 一致）。
    return str(value) or "gemini-embedding-001"


# 環境變數注入來源：讀「本次 load_settings 傳入的 mapping」而非全域 os.environ，
# 讓測試灌 dict 時不會漏讀真實環境變數。透過 contextvar 在 Settings() 建構期間傳遞。
_ENV_OVERRIDE: ContextVar[Mapping[str, str] | None] = ContextVar(
    "kinsun_env_override", default=None
)


class _MappingSettingsSource(PydanticBaseSettingsSource):
    """把每個欄位以「大寫欄位名」為鍵去注入的 mapping 取值（未設則留給欄位預設）。"""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        override = _ENV_OVERRIDE.get()
        self._env: Mapping[str, str] = os.environ if override is None else override

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        # 覆寫 __call__ 後不使用此逐欄取值路徑；仍需實作抽象方法。
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name in self.settings_cls.model_fields:
            key = name.upper()
            if key in self._env:
                values[name] = self._env[key]
        return values


class _BaseEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 只用「注入 mapping」來源；排除預設的 env／dotenv 來源，避免測試漏讀 os.environ。
        return (init_settings, _MappingSettingsSource(settings_cls))


class Settings(_BaseEnvSettings):
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    # 按用途配模型（✅ D-16 丁-5）：未設＝沿用 GEMINI_MODEL（見 _resolve_model_fallbacks）。
    gemini_model_safety: str = "gemini-3.5-flash-lite"
    gemini_model_summary: str = "gemini-3.5-flash-lite"
    asr_backend: str = "mock"
    asr_endpoint: str = ""
    asr_api_key: str = ""
    asr_timeout_seconds: float = 15.0
    gemini_timeout_seconds: float = 30.0
    memory_max_turns: int = 200
    timezone: str = "Asia/Taipei"
    longterm_embedding_model: str = "gemini-embedding-001"
    longterm_consolidation_hour: int = 0
    scheduler_tick_seconds: int = 60
    # 基準問候時間：真的鐘點，且須落在自適應上下限內（見 _validate_greeting_guardrails）。
    proactive_greeting_hour: Annotated[int, BeforeValidator(_hour("PROACTIVE_GREETING_HOUR"))] = 8
    proactive_inactivity_hour: int = 10
    proactive_inactivity_days: int = 2
    # 自適應問候（spec 2026-07-16）：預設開；關閉則全體回退 PROACTIVE_GREETING_HOUR。
    proactive_greeting_adaptive_enabled: Bool = True
    proactive_greeting_lookback_days: Annotated[
        int, BeforeValidator(_at_least_one("PROACTIVE_GREETING_LOOKBACK_DAYS"))
    ] = 14
    proactive_greeting_min_sample_days: Annotated[
        int, BeforeValidator(_at_least_one("PROACTIVE_GREETING_MIN_SAMPLE_DAYS"))
    ] = 5
    proactive_greeting_earliest_hour: Annotated[
        int, BeforeValidator(_hour("PROACTIVE_GREETING_EARLIEST_HOUR"))
    ] = 6
    proactive_greeting_latest_hour: Annotated[
        int, BeforeValidator(_hour("PROACTIVE_GREETING_LATEST_HOUR"))
    ] = 11
    proactive_greeting_max_shift_minutes: Annotated[
        int, BeforeValidator(_at_least_one("PROACTIVE_GREETING_MAX_SHIFT_MINUTES"))
    ] = 30
    proactive_greeting_lag_tolerance_minutes: Annotated[
        int, BeforeValidator(_at_least_one("PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES"))
    ] = 60
    invite_ttl_hours: int = 24
    invite_max_attempts: int = 5
    database_url: str = ""
    # 每進程連線池上限（✅ 庚-26／A-55）：總量公式見 .env.example 與 14 部署文檔。
    database_pool_max_size: int = 5
    longterm_top_k: int = 5
    longterm_health_top_k: int = 3
    # 記憶檢索重排（✅ D-40 丁-4）：LLM reranker，決議預設開；額度吃緊時可關。
    longterm_rerank_enabled: Bool = True
    binding_session_ttl_minutes: int = 10
    medication_morning_hour: int = 8
    medication_noon_hour: int = 12
    medication_evening_hour: int = 18
    medication_bedtime_hour: int = 21
    appointment_reminder_hour: int = 8
    rag_top_k: int = 5
    # 位置超過幾小時就不再採信、不注入 prompt（spec 2026-07-17）。只影響主動問候路徑。
    location_stale_after_hours: Annotated[
        int, BeforeValidator(_at_least_one("LOCATION_STALE_AFTER_HOURS"))
    ] = 2
    # 上網查證金鑰（spec 2026-07-14）：留空＝不註冊 web_search 工具（優雅降級）。
    tavily_api_key: str = ""
    # TDX 交通資料憑證：兩者皆留空＝不註冊公車／捷運／停車工具（優雅降級）；
    # 路線工具走免金鑰的 OSRM，不受此影響、永遠可用。
    tdx_client_id: str = ""
    tdx_client_secret: str = ""
    rag_content_policy: Annotated[str, BeforeValidator(_content_policy)] = "allowed_only"
    rag_embedding_model: Annotated[str, BeforeValidator(_embedding_model)] = "gemini-embedding-001"
    rag_refresh_enabled: Bool = False
    rag_refresh_cron: Annotated[str, BeforeValidator(_refresh_cron)] = "0 3 * * 0"
    rag_audit_retention_days: Annotated[
        int, BeforeValidator(_positive("RAG_AUDIT_RETENTION_DAYS"))
    ] = 90
    liff_channel_id: str = ""
    liff_timeout_seconds: float = 10.0
    rich_menu_id: str = ""
    binding_gate_enabled: Bool = True
    tts_backend: str = "bubble"
    tts_endpoint: str = ""
    tts_api_key: str = ""
    tts_timeout_seconds: float = 30.0
    tts_reply_text: Bool = True
    supabase_url: str = ""
    supabase_service_key: str = ""
    audio_bucket: str = "tts-audio"
    # 音檔本體保留天數；0＝不清理（開關保留）。2026-07-09 定案：維持 2 天清理。
    audio_retention_days: int = 2
    audio_upload_timeout_seconds: float = 10.0
    audio_signed_url_expires_seconds: int = 86400
    # 對講機單回合音檔上限（✅ D-26 env 化，原 10MB 寫死）。
    audio_max_upload_bytes: int = 10485760
    auth_rate_limit_max_attempts: int = 10
    # 危急信心門檻（✅ D-41 丙-6 env 化）。
    safety_confidence_mid: float = 0.4
    auth_rate_limit_window_seconds: float = 300.0
    asr_debug_show_transcript: Bool = False
    # ✅ D-11（甲-4）：文字輸入為正式功能（與語音同等對待），預設開；關閉為維運逃生口。
    line_text_input_enabled: Bool = True
    admin_api_key: str = ""
    admin_retention_days: int = 14
    # 內測模式總開關（spec 2026-07-12）：App 切換身分＋後台手動觸發；正式環境務必 false。
    internal_testing_enabled: Bool = False
    # 每晚反思（spec 2026-07-14）：預設開——反思是自動主線行為，此旗標為緊急關閉開關。
    reflection_enabled: Bool = True
    reflection_lookback_days: Annotated[
        int, BeforeValidator(_at_least_one("REFLECTION_LOOKBACK_DAYS"))
    ] = 7
    reflection_min_observed_days: Annotated[
        int, BeforeValidator(_at_least_one("REFLECTION_MIN_OBSERVED_DAYS"))
    ] = 3
    reflection_max_strategies: Annotated[
        int, BeforeValidator(_at_least_one("REFLECTION_MAX_STRATEGIES"))
    ] = 15
    reflection_response_window_minutes: Annotated[
        int, BeforeValidator(_at_least_one("REFLECTION_RESPONSE_WINDOW_MINUTES"))
    ] = 60
    reflection_max_turns: Annotated[int, BeforeValidator(_at_least_one("REFLECTION_MAX_TURNS"))] = (
        600
    )
    # 工程觀測 Opik（OPIK_ 前綴）：預設開啟；連不到 Opik 服務時會安靜降級為 no-op。
    opik_enabled: Bool = True
    opik_url_override: str = "http://localhost:5273/api"
    opik_workspace: str = "default"
    opik_project_name: str = "kinsun"
    # 啟用時的連線探測逾時（秒）：configure() 在此秒數內判定 Opik 是否可達；連不到就
    # 安靜降級（no-op），避免 Windows/macOS 開發機或 CI 無 Opik 服務時噴連線錯誤。
    opik_ping_timeout_seconds: float = 2.0

    @model_validator(mode="before")
    @classmethod
    def _resolve_model_fallbacks(cls, values: Any) -> Any:
        # safety／summary 未設（或空）＝沿用主模型（其自身亦回退預設）。
        if not isinstance(values, dict):
            return values
        model = values.get("gemini_model") or "gemini-3.5-flash-lite"
        if not values.get("gemini_model_safety"):
            values["gemini_model_safety"] = model
        if not values.get("gemini_model_summary"):
            values["gemini_model_summary"] = model
        return values

    @model_validator(mode="after")
    def _require_present(self) -> Settings:
        required = {
            "LINE_CHANNEL_SECRET": self.line_channel_secret,
            "LINE_CHANNEL_ACCESS_TOKEN": self.line_channel_access_token,
            "GEMINI_API_KEY": self.gemini_api_key,
            "DATABASE_URL": self.database_url,
        }
        for key, value in required.items():
            if not value:
                raise ConfigError(f"缺少必要環境變數：{key}")
        return self

    @model_validator(mode="after")
    def _validate_reflection_guardrails(self) -> Settings:
        # 證據門檻超出回顧視野＝沒有守則能通過門檻，反思每晚空轉卻不報錯（fail-fast 攔下）。
        if self.reflection_min_observed_days > self.reflection_lookback_days:
            raise ConfigError(
                f"REFLECTION_MIN_OBSERVED_DAYS（{self.reflection_min_observed_days}）不得大於 "
                f"REFLECTION_LOOKBACK_DAYS（{self.reflection_lookback_days}）："
                "證據門檻超出回顧視野時，沒有守則能通過門檻，反思會每晚空轉卻不報錯。"
            )
        return self

    @model_validator(mode="after")
    def _validate_greeting_guardrails(self) -> Settings:
        # 自適應問候的護欄：這機制會自動改變系統對長輩的行為時間，護欄比演算法重要——
        # 算錯了沒有護欄就是半夜三點吵醒人。以下不變量的失效都是靜默的，留到夜裡的 job
        # 才浮現時看不出任何異常，因此在載入當下就 fail-fast。
        earliest = self.proactive_greeting_earliest_hour
        latest = self.proactive_greeting_latest_hour
        # 上下限顛倒／相等＝夾取區間為空或退化，問候時間會被夾成荒謬的值。
        if earliest >= latest:
            raise ConfigError(
                f"PROACTIVE_GREETING_EARLIEST_HOUR（{earliest}）"
                f"必須小於 PROACTIVE_GREETING_LATEST_HOUR（{latest}）。"
            )
        # 基準值落在自己的上下限之外＝自相矛盾。夜間批次的護軌會把它夾回界內（縱深防禦，
        # 刻意保留），但那是靜默的補救；矛盾的設定要在啟動時就講清楚。
        if not earliest <= self.proactive_greeting_hour <= latest:
            raise ConfigError(
                f"PROACTIVE_GREETING_HOUR（{self.proactive_greeting_hour}）必須介於 "
                f"PROACTIVE_GREETING_EARLIEST_HOUR（{earliest}）與 "
                f"PROACTIVE_GREETING_LATEST_HOUR（{latest}）之間："
                "基準問候時間落在自己的護軌外，等於要求系統在被自己禁止的時間問候。"
            )
        # 步伐必須是掃描間隔的正倍數：步伐算完會經 greeting_time._align 對齊到半點，對齊會把
        # 非倍數的步伐吃掉或放大，兩種誤設都是靜默的。SLOT_MINUTES 取自唯一真實來源。
        max_shift = self.proactive_greeting_max_shift_minutes
        if max_shift % SLOT_MINUTES != 0:
            raise ConfigError(
                f"PROACTIVE_GREETING_MAX_SHIFT_MINUTES（{max_shift}）"
                f"必須是問候掃描間隔 {SLOT_MINUTES} 分的正倍數（如 {SLOT_MINUTES}、"
                f"{SLOT_MINUTES * 2}）："
                f"問候時間一律對齊半點，非倍數的步伐會被對齊吃掉或放大，且不會報錯——"
                f"小於 {SLOT_MINUTES} 會被捨回原點（問候時間永遠不動，自適應等同癱瘓）；"
                f"大於 {SLOT_MINUTES} 但非倍數會往上進位（實際位移超過你設定的上限）。"
            )
        # 往後的容忍度比往前的死區還緊＝設計意圖被反轉（問候後才有動靜是模糊訊號）。
        if self.proactive_greeting_lag_tolerance_minutes < max_shift:
            raise ConfigError(
                f"PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES"
                f"（{self.proactive_greeting_lag_tolerance_minutes}）"
                f"不得小於 PROACTIVE_GREETING_MAX_SHIFT_MINUTES（{max_shift}）："
                "往後的容忍度比往前的死區還鬆是刻意的設計（問候後才有動靜是模糊訊號），"
                "反過來設會讓往前調比往後調保守，與設計意圖相反。"
            )
        # 樣本門檻超出回顧視野＝永遠湊不到樣本，問候時間永遠不會調整，且不會報錯。
        if self.proactive_greeting_min_sample_days > self.proactive_greeting_lookback_days:
            raise ConfigError(
                f"PROACTIVE_GREETING_MIN_SAMPLE_DAYS（{self.proactive_greeting_min_sample_days}）"
                f"不得大於 PROACTIVE_GREETING_LOOKBACK_DAYS"
                f"（{self.proactive_greeting_lookback_days}）："
                "樣本門檻超出回顧視野時，永遠湊不到足夠樣本，問候時間永遠不會調整卻不報錯。"
            )
        return self


class RagWorkerSettings(_BaseEnvSettings):
    """獨立 RAG Worker 所需設定，不綁 LINE、語音、LIFF 或主動關懷。"""

    database_url: str = ""
    database_pool_max_size: Annotated[int, BeforeValidator(_positive("DATABASE_POOL_MAX_SIZE"))] = 5
    gemini_api_key: str = ""
    timezone: str = "Asia/Taipei"
    scheduler_tick_seconds: Annotated[int, BeforeValidator(_positive("SCHEDULER_TICK_SECONDS"))] = (
        60
    )
    rag_content_policy: Annotated[str, BeforeValidator(_content_policy)] = "allowed_only"
    rag_embedding_model: Annotated[str, BeforeValidator(_embedding_model)] = "gemini-embedding-001"
    rag_refresh_enabled: Bool = False
    rag_refresh_cron: Annotated[str, BeforeValidator(_refresh_cron)] = "0 3 * * 0"
    rag_audit_retention_days: Annotated[
        int, BeforeValidator(_positive("RAG_AUDIT_RETENTION_DAYS"))
    ] = 90

    @model_validator(mode="after")
    def _require_present(self) -> RagWorkerSettings:
        required = {
            "DATABASE_URL": self.database_url,
            "GEMINI_API_KEY": self.gemini_api_key,
        }
        for key, value in required.items():
            if not value:
                raise ConfigError(f"缺少必要環境變數：{key}")
        return self


def load_settings(env: Mapping[str, str]) -> Settings:
    token = _ENV_OVERRIDE.set(env)
    try:
        return Settings()
    finally:
        _ENV_OVERRIDE.reset(token)


def load_rag_worker_settings(env: Mapping[str, str]) -> RagWorkerSettings:
    """只載入 RAG 週更程序實際依賴，避免被其他 channel 的金鑰阻擋。"""
    token = _ENV_OVERRIDE.set(env)
    try:
        return RagWorkerSettings()
    finally:
        _ENV_OVERRIDE.reset(token)
