import pytest

from kinsun.config import ConfigError, Settings, load_settings

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
