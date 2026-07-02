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
    assert settings.memory_max_turns == 200
    assert settings.timezone == "Asia/Taipei"
    assert settings.embedding_model == "gemini-embedding-001"
    assert settings.consolidation_hour == 3
    assert settings.scheduler_tick_seconds == 60
    assert settings.greeting_hour == 8
    assert settings.inactivity_hour == 10
    assert settings.inactivity_days == 2
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
    assert settings.liff_channel_id == ""
    assert settings.liff_timeout_seconds == 10
    assert settings.rich_menu_id == ""
    assert settings.binding_gate_enabled is True


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
