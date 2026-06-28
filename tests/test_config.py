import pytest

from kinsun.config import ConfigError, Settings, load_settings

BASE_ENV = {
    "LINE_CHANNEL_SECRET": "secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "token",
    "GEMINI_API_KEY": "key",
}


def test_load_settings_reads_required_and_defaults():
    settings = load_settings(BASE_ENV)
    assert isinstance(settings, Settings)
    assert settings.line_channel_secret == "secret"
    assert settings.asr_backend == "mock"
    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert settings.memory_db_path == "kinsun_memory.db"
    assert settings.memory_max_turns == 200
    assert settings.timezone == "Asia/Taipei"
    assert settings.knowledge_db_path == "kinsun_knowledge.db"
    assert settings.episodic_db_path == "kinsun_episodic.db"
    assert settings.episodic_top_k == 3
    assert settings.embedding_model == "gemini-embedding-001"
    assert settings.consolidation_hour == 3
    assert settings.scheduler_tick_seconds == 60
    assert settings.greeting_hour == 8
    assert settings.inactivity_hour == 10
    assert settings.inactivity_days == 2


def test_load_settings_missing_required_raises():
    with pytest.raises(ConfigError):
        load_settings({})


def test_load_settings_overrides_from_env():
    env = {**BASE_ENV, "ASR_BACKEND": "dgx", "ASR_ENDPOINT": "http://dgx:8001"}
    settings = load_settings(env)
    assert settings.asr_backend == "dgx"
    assert settings.asr_endpoint == "http://dgx:8001"
