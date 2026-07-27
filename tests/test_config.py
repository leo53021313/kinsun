import os
import subprocess
import sys
from pathlib import Path

import pytest

from kinsun.config import (
    ConfigError,
    Settings,
    load_dotenv,
    load_rag_worker_settings,
    load_settings,
)

BASE_ENV = {
    "LINE_CHANNEL_SECRET": "secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "token",
    "GEMINI_API_KEY": "key",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}


def test_load_settings_reads_required_and_defaults():
    settings = load_settings(BASE_ENV)
    assert isinstance(settings, Settings)
    assert settings.line_channel_secret == "secret"
    assert settings.asr_backend == "mock"
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.gemini_model_safety == "gemini-3.5-flash-lite"  # 未設＝沿用主模型
    assert settings.gemini_model_summary == "gemini-3.5-flash-lite"
    assert settings.memory_max_turns == 200
    assert settings.timezone == "Asia/Taipei"
    assert settings.longterm_embedding_model == "gemini-embedding-001"
    assert settings.longterm_consolidation_hour == 0  # ✅ 庚-48：00:05 整理，盲窗 5 分
    assert settings.scheduler_tick_seconds == 60
    assert settings.proactive_greeting_hour == 8
    assert settings.proactive_inactivity_hour == 10
    assert settings.proactive_inactivity_days == 2
    assert settings.invite_ttl_hours == 24
    assert settings.invite_max_attempts == 5
    assert settings.database_url == "postgresql://u:p@h:5432/db"
    assert settings.longterm_top_k == 5
    assert settings.binding_session_ttl_minutes == 10
    assert settings.medication_morning_hour == 8
    assert settings.medication_noon_hour == 12
    assert settings.medication_evening_hour == 18
    assert settings.medication_bedtime_hour == 21
    assert settings.appointment_reminder_hour == 8
    assert settings.rag_top_k == 5
    assert settings.location_stale_after_hours == 2  # 保守門檻：只影響主動問候路徑
    assert settings.rag_content_policy == "allowed_only"
    assert settings.rag_embedding_model == "gemini-embedding-001"
    assert settings.rag_refresh_enabled is False
    assert settings.rag_refresh_cron == "0 3 * * 0"
    assert settings.rag_audit_retention_days == 90
    assert settings.liff_channel_id == ""
    assert settings.liff_timeout_seconds == 10
    assert settings.rich_menu_id == ""
    assert settings.binding_gate_enabled is True
    assert settings.tts_backend == "bubble"
    assert settings.tts_endpoint == ""
    assert settings.tts_timeout_seconds == 30
    assert settings.tts_reply_text is True
    assert settings.supabase_url == ""
    assert settings.supabase_service_key == ""
    assert settings.audio_bucket == "tts-audio"
    assert settings.audio_retention_days == 2  # 預設 2 天清理；0＝不清理開關保留
    assert settings.audio_upload_timeout_seconds == 10
    assert settings.audio_max_upload_bytes == 10 * 1024 * 1024
    assert settings.safety_confidence_mid == 0.4
    # 濫用審核預設開（Leo 核定 2026-07-25）：這是會攔掉長輩發話、且每輪多一次 LLM
    # 呼叫的路徑，預設值的任何更動都必須是刻意的，故在此釘死。
    assert settings.safety_moderation_enabled is True
    assert settings.safety_moderation_min_confidence == 0.7
    assert settings.asr_api_key == ""
    assert settings.tts_api_key == ""
    assert settings.asr_debug_show_transcript is False
    assert settings.line_text_input_enabled is True
    assert settings.admin_api_key == ""
    assert settings.admin_retention_days == 14


def test_location_stale_after_hours_is_overridable():
    settings = load_settings({**BASE_ENV, "LOCATION_STALE_AFTER_HOURS": "6"})
    assert settings.location_stale_after_hours == 6


def test_location_stale_after_hours_rejects_zero():
    # 0 會讓位置永遠過期、功能靜默失效；要關閉功能應該不給 App 定位權限，不是設 0。
    with pytest.raises(ConfigError):
        load_settings({**BASE_ENV, "LOCATION_STALE_AFTER_HOURS": "0"})


def test_load_settings_requires_database_url():
    env = {
        "LINE_CHANNEL_SECRET": "s",
        "LINE_CHANNEL_ACCESS_TOKEN": "t",
        "GEMINI_API_KEY": "k",
    }
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_rejects_unknown_rag_content_policy():
    with pytest.raises(ConfigError, match="RAG_CONTENT_POLICY"):
        load_settings({**BASE_ENV, "RAG_CONTENT_POLICY": "public_demo"})


# ── 語音後端白名單：打錯字必須啟動失敗，不可靜默降級 ──
#
# `build_asr_client` 對任何非 "dgx" 的值一律回 MockAsrClient，而它對任何音檔都回傳寫死的
# 「今天天氣真好」。少打一個字母＝長輩每一句話都被聽成那句，金孫照著回，而且一行錯誤
# 都不印。fail-fast 的門檻與 GEMINI_API_KEY 缺漏同級。


@pytest.mark.parametrize("value", ["dgxx", "DGX2", "真的", " "])
def test_load_settings_rejects_unknown_asr_backend(value):
    with pytest.raises(ConfigError, match="ASR_BACKEND"):
        load_settings({**BASE_ENV, "ASR_BACKEND": value})


@pytest.mark.parametrize("value", ["bubbles", "dgx_", "真的"])
def test_load_settings_rejects_unknown_tts_backend(value):
    with pytest.raises(ConfigError, match="TTS_BACKEND"):
        load_settings({**BASE_ENV, "TTS_BACKEND": value})


@pytest.mark.parametrize(("raw", "expected"), [("DGX", "dgx"), (" dgx ", "dgx"), ("Mock", "mock")])
def test_asr_backend_is_normalised_not_rejected(raw, expected):
    """大小寫與前後空白是無害的變體，正規化即可——真正要擋的是拼錯的值。"""
    assert load_settings({**BASE_ENV, "ASR_BACKEND": raw}).asr_backend == expected


@pytest.mark.parametrize("value", ["不是 cron", "0 25 * * *", "* * *"])
def test_load_settings_rejects_invalid_rag_refresh_cron(value):
    with pytest.raises(ConfigError, match="RAG_REFRESH_CRON"):
        load_settings({**BASE_ENV, "RAG_REFRESH_CRON": value})


def test_load_settings_empty_rag_refresh_cron_uses_default():
    assert load_settings({**BASE_ENV, "RAG_REFRESH_CRON": ""}).rag_refresh_cron == "0 3 * * 0"


@pytest.mark.parametrize("value", ["0", "-1", "不是數字"])
def test_load_settings_rejects_invalid_rag_audit_retention_days(value):
    with pytest.raises(ConfigError, match="RAG_AUDIT_RETENTION_DAYS"):
        load_settings({**BASE_ENV, "RAG_AUDIT_RETENTION_DAYS": value})


def test_load_settings_missing_required_raises():
    with pytest.raises(ConfigError):
        load_settings({})


def test_load_settings_overrides_from_env():
    env = {**BASE_ENV, "ASR_BACKEND": "dgx", "ASR_ENDPOINT": "http://dgx:8001"}
    settings = load_settings(env)
    assert settings.asr_backend == "dgx"
    assert settings.asr_endpoint == "http://dgx:8001"


def test_load_settings_binding_gate_disabled():
    for raw in ("false", "0", "no", "False"):
        settings = load_settings({**BASE_ENV, "BINDING_GATE_ENABLED": raw})
        assert settings.binding_gate_enabled is False, raw


def test_load_settings_binding_gate_enabled_values():
    for raw in ("true", "1", "yes", "True"):
        settings = load_settings({**BASE_ENV, "BINDING_GATE_ENABLED": raw})
        assert settings.binding_gate_enabled is True, raw


def test_load_settings_tts_reply_text_false():
    for raw in ("false", "0", "no", "False"):
        settings = load_settings({**BASE_ENV, "TTS_REPLY_TEXT": raw})
        assert settings.tts_reply_text is False, raw


def test_load_settings_tts_overrides():
    env = {**BASE_ENV, "TTS_BACKEND": "dgx", "TTS_ENDPOINT": "http://dgx:8002/synthesize"}
    settings = load_settings(env)
    assert settings.tts_backend == "dgx"
    assert settings.tts_endpoint == "http://dgx:8002/synthesize"


def test_load_dotenv_fills_missing_only(tmp_path):
    envfile = tmp_path / ".env"
    envfile.write_text(
        "# 註解\n\nA=1\nB = two \n"
        "DATABASE_URL=postgresql://u:p@h:5432/db?sslmode=require\n"
        "EXISTING=fromfile\n",
        encoding="utf-8",
    )
    environ = {"EXISTING": "fromenv"}
    load_dotenv(envfile, environ=environ)
    assert environ["A"] == "1"
    assert environ["B"] == "two"  # 去除前後空白
    assert environ["DATABASE_URL"].endswith("sslmode=require")  # 值含 = 不被切斷
    assert environ["EXISTING"] == "fromenv"  # 既有變數不被覆蓋


def test_load_dotenv_missing_file_is_noop(tmp_path):
    environ = {}
    load_dotenv(tmp_path / "nope.env", environ=environ)
    assert environ == {}


def test_rag_worker_settings_do_not_require_unrelated_channel_secrets():
    settings = load_rag_worker_settings(
        {
            "DATABASE_URL": "postgresql://rag-worker/example",
            "GEMINI_API_KEY": "test-gemini-key",
            "RAG_CONTENT_POLICY": "classroom_demo",
            "RAG_REFRESH_ENABLED": "true",
        }
    )

    assert settings.database_url == "postgresql://rag-worker/example"
    assert settings.rag_refresh_enabled is True
    assert settings.rag_refresh_cron == "0 3 * * 0"
    assert settings.rag_content_policy == "classroom_demo"


@pytest.mark.parametrize("missing_key", ["DATABASE_URL", "GEMINI_API_KEY"])
def test_rag_worker_settings_require_only_their_external_dependencies(missing_key):
    env = {
        "DATABASE_URL": "postgresql://rag-worker/example",
        "GEMINI_API_KEY": "test-gemini-key",
    }
    del env[missing_key]

    with pytest.raises(ConfigError, match=missing_key):
        load_rag_worker_settings(env)


def test_load_settings_asr_debug_show_transcript_default_false():
    assert load_settings(BASE_ENV).asr_debug_show_transcript is False


def test_load_settings_asr_debug_show_transcript_true():
    s = load_settings({**BASE_ENV, "ASR_DEBUG_SHOW_TRANSCRIPT": "true"})
    assert s.asr_debug_show_transcript is True


def test_load_settings_line_text_input_default_true():
    """✅ D-11（甲-4）：文字輸入為正式功能，預設開。"""
    assert load_settings(BASE_ENV).line_text_input_enabled is True


def test_load_settings_line_text_input_enabled_values():
    for raw in ("true", "1", "yes", "True"):
        s = load_settings({**BASE_ENV, "LINE_TEXT_INPUT_ENABLED": raw})
        assert s.line_text_input_enabled is True, raw


def test_load_settings_line_text_input_disabled_values():
    for raw in ("false", "0", "no", "False"):
        s = load_settings({**BASE_ENV, "LINE_TEXT_INPUT_ENABLED": raw})
        assert s.line_text_input_enabled is False, raw


def test_gemini_model_per_purpose_override():
    """✅ D-16（丁-5）：分級／摘要可各自換模型，未設沿用主模型。"""
    s = load_settings({**BASE_ENV, "GEMINI_MODEL_SAFETY": "gemini-3.1-pro"})
    assert s.gemini_model_safety == "gemini-3.1-pro"
    assert s.gemini_model_summary == "gemini-3.5-flash-lite"


def test_internal_testing_enabled_defaults_false_and_parses():
    """內測總開關（spec 2026-07-12 §3.1）：預設關；true 才開。"""
    assert load_settings(BASE_ENV).internal_testing_enabled is False
    on = load_settings({**BASE_ENV, "INTERNAL_TESTING_ENABLED": "true"})
    assert on.internal_testing_enabled is True


def test_database_pool_max_size_default_and_override():
    """✅ 庚-26（A-55）：連線池上限可調。

    總量公式：WEB_WORKERS×本值＋排程 worker×本值 ≤ Supabase 直連上限 60。
    """
    settings = load_settings(BASE_ENV)
    assert settings.database_pool_max_size == 5
    settings = load_settings({**BASE_ENV, "DATABASE_POOL_MAX_SIZE": "3"})
    assert settings.database_pool_max_size == 3


def test_longterm_health_top_k_default_and_override():
    """✅ 庚-38（A-22）：健康記憶檢索條數接 settings（原硬編建構子預設）。"""
    assert load_settings(BASE_ENV).longterm_health_top_k == 3
    assert load_settings({**BASE_ENV, "LONGTERM_HEALTH_TOP_K": "6"}).longterm_health_top_k == 6


def test_tavily_api_key_defaults_to_empty():
    # 留空＝不註冊 web_search 工具（優雅降級），見 composition.build_tool_registry。
    assert load_settings(BASE_ENV).tavily_api_key == ""


def test_tavily_api_key_read_from_env():
    settings = load_settings({**BASE_ENV, "TAVILY_API_KEY": "tvly-abc"})
    assert settings.tavily_api_key == "tvly-abc"


def test_reflection_settings_have_defaults():
    settings = load_settings(BASE_ENV)
    assert settings.reflection_enabled is True
    assert settings.reflection_lookback_days == 7
    assert settings.reflection_min_observed_days == 3
    assert settings.reflection_max_strategies == 15
    assert settings.reflection_response_window_minutes == 60
    assert settings.reflection_max_turns == 600


def test_reflection_can_be_switched_off():
    settings = load_settings({**BASE_ENV, "REFLECTION_ENABLED": "false"})
    assert settings.reflection_enabled is False


@pytest.mark.parametrize("raw", ["off", "OFF", "Off", "n", "N", "", "   "])
def test_reflection_kill_switch_honours_off_and_blank(raw):
    """`off`／空值必須真的關掉——這是反思唯一的緊急關閉開關，不能給假的安全感。

    反思自動生效、無人審、每晚自動跑。凌晨三點發現守則學歪、要立刻關掉的人打了
    `REFLECTION_ENABLED=off`，若這裡把它讀成 True，他會得到「已關閉」的錯覺，而它照跑。
    空值（`REFLECTION_ENABLED=`）同理——那是「我把值刪掉了」的意思，不是「請開著」。
    """
    settings = load_settings({**BASE_ENV, "REFLECTION_ENABLED": raw})
    assert settings.reflection_enabled is False, raw


@pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "y", "on"])
def test_reflection_stays_on_for_truthy_values(raw):
    settings = load_settings({**BASE_ENV, "REFLECTION_ENABLED": raw})
    assert settings.reflection_enabled is True, raw


def test_reflection_min_observed_days_must_not_exceed_lookback():
    """證據門檻大於回顧視野＝沒有守則能通過門檻，反思每晚空轉卻不報錯（fail-fast 攔下）。"""
    env = {**BASE_ENV, "REFLECTION_MIN_OBSERVED_DAYS": "30", "REFLECTION_LOOKBACK_DAYS": "7"}
    with pytest.raises(ConfigError) as exc:
        load_settings(env)
    message = str(exc.value)
    assert "REFLECTION_MIN_OBSERVED_DAYS" in message
    assert "REFLECTION_LOOKBACK_DAYS" in message
    assert "30" in message  # 訊息要自解釋：含實際數值
    assert "7" in message


def test_reflection_min_observed_days_equal_lookback_is_allowed():
    """邊界：門檻＝回顧視野仍可成立（守則需每天都被觀察到），不該被擋。"""
    env = {**BASE_ENV, "REFLECTION_MIN_OBSERVED_DAYS": "7", "REFLECTION_LOOKBACK_DAYS": "7"}
    settings = load_settings(env)
    assert settings.reflection_min_observed_days == 7
    assert settings.reflection_lookback_days == 7


@pytest.mark.parametrize(
    "key",
    [
        "REFLECTION_LOOKBACK_DAYS",
        "REFLECTION_MIN_OBSERVED_DAYS",
        "REFLECTION_MAX_STRATEGIES",
        "REFLECTION_RESPONSE_WINDOW_MINUTES",
        "REFLECTION_MAX_TURNS",
    ],
)
@pytest.mark.parametrize("raw", ["0", "-1"])
def test_reflection_numeric_settings_must_be_at_least_one(key: str, raw: str):
    """0 或負數會讓反思靜默失效或行為未定義；啟動時就要擋。"""
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, key: raw})
    message = str(exc.value)
    assert key in message
    assert raw in message


def test_reflection_numeric_settings_accept_legal_overrides():
    """合法覆寫不受驗證影響。"""
    env = {
        **BASE_ENV,
        "REFLECTION_LOOKBACK_DAYS": "14",
        "REFLECTION_MIN_OBSERVED_DAYS": "1",
        "REFLECTION_MAX_STRATEGIES": "1",
        "REFLECTION_RESPONSE_WINDOW_MINUTES": "1",
        "REFLECTION_MAX_TURNS": "1000",
    }
    settings = load_settings(env)
    assert settings.reflection_lookback_days == 14
    assert settings.reflection_min_observed_days == 1
    assert settings.reflection_max_strategies == 1
    assert settings.reflection_response_window_minutes == 1
    assert settings.reflection_max_turns == 1000


def test_adaptive_greeting_settings_have_defaults():
    settings = load_settings(BASE_ENV)
    assert settings.proactive_greeting_adaptive_enabled is True
    assert settings.proactive_greeting_lookback_days == 14
    assert settings.proactive_greeting_min_sample_days == 5
    assert settings.proactive_greeting_earliest_hour == 6
    assert settings.proactive_greeting_latest_hour == 11
    assert settings.proactive_greeting_max_shift_minutes == 30
    assert settings.proactive_greeting_lag_tolerance_minutes == 60


def test_greeting_lag_tolerance_must_not_be_tighter_than_max_shift():
    """往後的容忍度比往前的死區還緊＝設計意圖被反轉，啟動即失敗。

    容忍度之所以存在，是因為「問候後才有動靜」是模糊訊號（分不出「還沒醒」與
    「只是慢慢看手機」），往後調必須比往前調保守。若 lag_tolerance < max_shift，
    往前調反而變得比往後調保守——機制還在跑、不報錯，但方向反了。
    """
    with pytest.raises(ConfigError) as exc:
        load_settings(
            {
                **BASE_ENV,
                "PROACTIVE_GREETING_MAX_SHIFT_MINUTES": "30",
                "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES": "15",
            }
        )
    message = str(exc.value)
    assert "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES" in message
    assert "PROACTIVE_GREETING_MAX_SHIFT_MINUTES" in message
    assert "15" in message and "30" in message  # 訊息要自解釋：含實際數值


def test_greeting_lag_tolerance_equal_to_max_shift_is_allowed():
    """邊界：兩者相等仍成立（等於兩個方向同門檻，是舊行為），不該被擋。"""
    settings = load_settings(
        {
            **BASE_ENV,
            "PROACTIVE_GREETING_MAX_SHIFT_MINUTES": "30",
            "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES": "30",
        }
    )
    assert settings.proactive_greeting_lag_tolerance_minutes == 30


@pytest.mark.parametrize("raw", ["5", "10", "14", "15", "45", "40"])
def test_greeting_max_shift_must_be_a_multiple_of_the_scan_slot(raw):
    """MAX_SHIFT 非 30 的倍數＝兩種靜默失效，啟動即失敗。

    步伐算完會經 `_align` 對齊到半點（問候 job 每半小時掃描，存 07:45 卻在 08:00
    問候是對後台說謊），而對齊會把不是 30 倍數的步伐吃掉或放大——兩種誤設都不報錯：

    * ≤ 15：每一步都被捨回原點 → 問候時間**永遠不動**。設定看起來生效了、機制看
      起來在跑，實際上自適應完全癱瘓（實測 5／10／14／15 皆然）。
    * 非 30 倍數（如 45）：對齊往上進位 → **實際位移超過宣稱的上限**（實測 45 →
      08:00 直接跳 09:00，位移 60 分）。稽核「30 分速率限制有被遵守嗎」會查無此據。
    """
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, "PROACTIVE_GREETING_MAX_SHIFT_MINUTES": raw})
    message = str(exc.value)
    assert "PROACTIVE_GREETING_MAX_SHIFT_MINUTES" in message
    assert raw in message and "30" in message  # 訊息要自解釋：含實際數值與掃描間隔


def test_greeting_max_shift_accepts_positive_multiples_of_the_scan_slot():
    """邊界：60 是 30 的正倍數 → 放行（實測位移正好 60 分，與宣稱一致）。"""
    settings = load_settings(
        {
            **BASE_ENV,
            "PROACTIVE_GREETING_MAX_SHIFT_MINUTES": "60",
            "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES": "60",
        }
    )
    assert settings.proactive_greeting_max_shift_minutes == 60


def test_greeting_lag_tolerance_is_not_bound_to_the_scan_slot():
    """LAG_TOLERANCE 刻意不受倍數限制——它只是門檻，不參與 `_align`。

    把倍數限制「順手」套到它身上會擋掉完全合法的設定（如 45 分容忍度）。兩者的
    角色不同：MAX_SHIFT 是步伐（會被對齊），LAG_TOLERANCE 只決定「要不要動」。
    """
    settings = load_settings(
        {
            **BASE_ENV,
            "PROACTIVE_GREETING_MAX_SHIFT_MINUTES": "30",
            "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES": "45",
        }
    )
    assert settings.proactive_greeting_lag_tolerance_minutes == 45


def test_adaptive_greeting_can_be_switched_off():
    settings = load_settings({**BASE_ENV, "PROACTIVE_GREETING_ADAPTIVE_ENABLED": "false"})
    assert settings.proactive_greeting_adaptive_enabled is False


@pytest.mark.parametrize("raw", ["off", "OFF", "Off", "n", "N", "", "   "])
def test_adaptive_greeting_kill_switch_honours_off_and_blank(raw):
    """`off`／空值必須真的關掉——這是自適應問候唯一的緊急關閉開關，不能給假的安全感。

    這東西會自動改變系統對長輩的行為時間、無人審。要立刻退回全體統一時間的人打了
    `PROACTIVE_GREETING_ADAPTIVE_ENABLED=off`，若這裡讀成 True，他會得到「已關閉」的
    錯覺，而它照調。空值同理——那是「我把值刪掉了」，不是「請開著」。
    """
    settings = load_settings({**BASE_ENV, "PROACTIVE_GREETING_ADAPTIVE_ENABLED": raw})
    assert settings.proactive_greeting_adaptive_enabled is False, raw


def test_greeting_hour_bounds_must_be_ordered():
    with pytest.raises(ConfigError, match="PROACTIVE_GREETING_EARLIEST_HOUR"):
        load_settings(
            {
                **BASE_ENV,
                "PROACTIVE_GREETING_EARLIEST_HOUR": "11",
                "PROACTIVE_GREETING_LATEST_HOUR": "6",
            }
        )


def test_greeting_hour_bounds_must_not_be_equal():
    """邊界：上下限相等＝夾取區間退化成單一時刻，四道護欄之一形同虛設；一併擋下。"""
    with pytest.raises(ConfigError) as exc:
        load_settings(
            {
                **BASE_ENV,
                "PROACTIVE_GREETING_EARLIEST_HOUR": "8",
                "PROACTIVE_GREETING_LATEST_HOUR": "8",
            }
        )
    message = str(exc.value)
    assert "PROACTIVE_GREETING_EARLIEST_HOUR" in message
    assert "PROACTIVE_GREETING_LATEST_HOUR" in message
    assert "8" in message  # 訊息要自解釋：含實際數值


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("PROACTIVE_GREETING_EARLIEST_HOUR", "-5"),
        ("PROACTIVE_GREETING_LATEST_HOUR", "24"),  # 邊界＋1
        ("PROACTIVE_GREETING_LATEST_HOUR", "99"),
    ],
)
def test_greeting_hour_bounds_must_be_a_real_hour(key, raw):
    """鐘點必須是真的鐘點（0..23）——順序檢查涵蓋不到這件事。

    順序檢查只約束「兩者的關係」，不約束「各自的範圍」：`EARLIEST=-5` 配上預設的
    `LATEST=11` 依然滿足 -5 < 11，於是靜默放行。這道護欄是四道裡唯一負責把統計算出的
    時間夾住的一道，夾取區間一旦變成 [-5, 99] 就等於沒有夾取——任何時間都原封不動通
    過，而且不報錯，系統看起來還在自適應。
    """
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, key: raw})
    message = str(exc.value)
    assert key in message
    assert raw in message  # 訊息要自解釋：含實際數值


def test_greeting_hour_bounds_reject_out_of_range_pair_that_passes_the_order_check():
    """`-5` 配 `99` 同時滿足順序檢查，卻是「等於沒有夾取」的區間；範圍驗證必須先擋下。"""
    with pytest.raises(ConfigError, match="PROACTIVE_GREETING_EARLIEST_HOUR"):
        load_settings(
            {
                **BASE_ENV,
                "PROACTIVE_GREETING_EARLIEST_HOUR": "-5",
                "PROACTIVE_GREETING_LATEST_HOUR": "99",
            }
        )


@pytest.mark.parametrize(
    ("key", "raw", "attribute"),
    [
        # 0 點是合法鐘點——這正是不能沿用 `_require_positive_int`（`< 1` 即擋）的全部理由。
        ("PROACTIVE_GREETING_EARLIEST_HOUR", "0", "proactive_greeting_earliest_hour"),
        ("PROACTIVE_GREETING_LATEST_HOUR", "23", "proactive_greeting_latest_hour"),
    ],
)
def test_greeting_hour_bounds_accept_legal_edges(key, raw, attribute):
    """範圍驗證不得誤擋合法邊界：0 與 23 都是真的鐘點。"""
    settings = load_settings({**BASE_ENV, key: raw})
    assert getattr(settings, attribute) == int(raw)


@pytest.mark.parametrize("raw", ["25", "-3", "99"])
def test_greeting_hour_itself_must_be_a_real_hour(raw: str):
    """`PROACTIVE_GREETING_HOUR` 也必須是真的鐘點——前一個 commit 只顧到上下限。

    上下限有 `_require_hour`，它卻還是裸的 `int()`：`25`、`-3`、`99` 全部照收。
    它是自適應關閉時全體長輩的問候時間，也是 Task E 餵給計算核心的現行值。
    """
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, "PROACTIVE_GREETING_HOUR": raw})
    message = str(exc.value)
    assert "PROACTIVE_GREETING_HOUR" in message
    assert raw in message  # 訊息要自解釋：含實際數值


@pytest.mark.parametrize("raw", ["5", "12"])
def test_greeting_hour_must_sit_inside_its_own_guardrails(raw: str):
    """設定錯誤要啟動即失敗，不要靠夜間批次默默夾回。

    `PROACTIVE_GREETING_HOUR=5` 配下限 6 是矛盾的設定。夜間批次的護軌會把它夾到
    6 點（縱深防禦，該留著），但維運看到的是「我設了 5 點，系統卻在 6 點問候」
    ——看起來像程式壞了。矛盾的設定應該在啟動時就講清楚。
    """
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, "PROACTIVE_GREETING_HOUR": raw})
    message = str(exc.value)
    assert "PROACTIVE_GREETING_HOUR" in message
    assert raw in message
    assert "6" in message and "11" in message  # 要含實際的上下限值


@pytest.mark.parametrize("raw", ["6", "8", "11"])
def test_greeting_hour_accepts_the_guardrail_edges(raw: str):
    """邊界不得誤擋：等於上限或下限都是合法設定。"""
    settings = load_settings({**BASE_ENV, "PROACTIVE_GREETING_HOUR": raw})
    assert settings.proactive_greeting_hour == int(raw)


def test_greeting_sample_days_must_fit_the_lookback_window():
    with pytest.raises(ConfigError, match="PROACTIVE_GREETING_MIN_SAMPLE_DAYS"):
        load_settings(
            {
                **BASE_ENV,
                "PROACTIVE_GREETING_LOOKBACK_DAYS": "3",
                "PROACTIVE_GREETING_MIN_SAMPLE_DAYS": "5",
            }
        )


def test_greeting_sample_days_equal_lookback_is_allowed():
    """邊界：門檻＝回顧視野仍可成立（每天都要有活躍才調整），不該被擋。"""
    env = {
        **BASE_ENV,
        "PROACTIVE_GREETING_LOOKBACK_DAYS": "5",
        "PROACTIVE_GREETING_MIN_SAMPLE_DAYS": "5",
    }
    settings = load_settings(env)
    assert settings.proactive_greeting_lookback_days == 5
    assert settings.proactive_greeting_min_sample_days == 5


@pytest.mark.parametrize(
    "key",
    [
        "PROACTIVE_GREETING_LOOKBACK_DAYS",
        "PROACTIVE_GREETING_MIN_SAMPLE_DAYS",
        "PROACTIVE_GREETING_MAX_SHIFT_MINUTES",
        "PROACTIVE_GREETING_LAG_TOLERANCE_MINUTES",
    ],
)
@pytest.mark.parametrize("raw", ["0", "-1"])
def test_greeting_numeric_settings_must_be_at_least_one(key: str, raw: str):
    """0 或負數會讓自適應問候靜默失效或行為未定義；啟動時就要擋。"""
    with pytest.raises(ConfigError) as exc:
        load_settings({**BASE_ENV, key: raw})
    message = str(exc.value)
    assert key in message
    assert raw in message


def test_importing_config_does_not_pull_in_the_database_driver():
    """config 是全庫最低層模組，import 它不得把資料庫驅動拖進來。

    這條測試是本專案唯一擋得住「相依鏈悄悄長回來」的防線，請不要刪。背景：

    * config 曾為了讓 SLOT_MINUTES 只有一份真實來源而 import greeting_time，結果
      沿著 greeting_time → memory.shortterm → db 一路把 psycopg（90＋子模組）與連線池
      拉進最低層。常數模組 proactive/constants.py 就是為了斬斷這條鏈而存在。
    * 真正的代價不只是啟動變慢：只要有人讓 db.py／llm.py／memory/shortterm.py 其中
      一支 import config（完全合理的需求），就會形成硬循環匯入，啟動即炸。
      這種錯誤在 code review 時幾乎看不出來——它藏在兩個模組的 import 之間。

    ⚠️ 必須用子行程測。同一個 pytest session 裡別的測試早就把 psycopg 匯入
    sys.modules 了，在本行程內斷言只會拿到別人的匯入結果，永遠是假失敗或假成功。
    """
    root = Path(__file__).resolve().parents[1]
    # 本專案非套件、不安裝（見 pyproject 的 pythonpath 設定），子行程要自己指出 src。
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    probe = (
        "import sys\n"
        "import kinsun.config\n"
        "print('\\n'.join(sorted(m for m in sys.modules if 'psycopg' in m)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, f"子行程匯入 config 失敗：{result.stderr}"
    leaked = result.stdout.split()
    assert leaked == [], (
        "import kinsun.config 把資料庫驅動拉進來了，相依鏈又長回來了：\n"
        + "\n".join(leaked)
        + "\n\n請找出 config 新增的那條 import，改為只依賴無相依的常數／純函式模組"
        "（如 kinsun.proactive.constants）。"
    )


def test_opik_settings_default_enabled():
    settings = load_settings(BASE_ENV)
    assert settings.opik_enabled is True
    assert settings.opik_url_override == "http://localhost:5273/api"
    assert settings.opik_workspace == "default"
    assert settings.opik_project_name == "kinsun"
    assert settings.opik_ping_timeout_seconds == 2.0


def test_opik_enabled_parses_falsy():
    env = {**BASE_ENV, "OPIK_ENABLED": "false", "OPIK_PROJECT_NAME": "kinsun-dev"}
    settings = load_settings(env)
    assert settings.opik_enabled is False
    assert settings.opik_project_name == "kinsun-dev"


def test_schedule_settings_defaults():
    settings = load_settings(BASE_ENV)
    assert settings.schedule_max_active_per_elder == 20
    assert settings.schedule_dispatch_window_seconds == 90
    assert settings.schedule_max_days_ahead == 365


def test_schedule_settings_overridable():
    settings = load_settings(
        {
            **BASE_ENV,
            "SCHEDULE_MAX_ACTIVE_PER_ELDER": "5",
            "SCHEDULE_DISPATCH_WINDOW_SECONDS": "120",
            "SCHEDULE_MAX_DAYS_AHEAD": "30",
        }
    )
    assert settings.schedule_max_active_per_elder == 5
    assert settings.schedule_dispatch_window_seconds == 120
    assert settings.schedule_max_days_ahead == 30


def test_schedule_dispatch_window_rejects_zero():
    with pytest.raises(ConfigError, match="SCHEDULE_DISPATCH_WINDOW_SECONDS"):
        load_settings({**BASE_ENV, "SCHEDULE_DISPATCH_WINDOW_SECONDS": "0"})
