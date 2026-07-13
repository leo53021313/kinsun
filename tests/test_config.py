import pytest

from kinsun.config import ConfigError, Settings, load_dotenv, load_settings

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
    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert settings.gemini_model_safety == "gemini-3.1-flash-lite"  # 未設＝沿用主模型
    assert settings.gemini_model_summary == "gemini-3.1-flash-lite"
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
    assert settings.asr_api_key == ""
    assert settings.tts_api_key == ""
    assert settings.asr_debug_show_transcript is False
    assert settings.line_text_input_enabled is True
    assert settings.admin_api_key == ""
    assert settings.admin_retention_days == 14


def test_load_settings_requires_database_url():
    env = {
        "LINE_CHANNEL_SECRET": "s",
        "LINE_CHANNEL_ACCESS_TOKEN": "t",
        "GEMINI_API_KEY": "k",
    }
    with pytest.raises(ConfigError):
        load_settings(env)


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
    assert s.gemini_model_summary == "gemini-3.1-flash-lite"


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
