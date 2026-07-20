from dataclasses import dataclass

from kinsun.tracing import client as tracing_client


@dataclass
class _S:
    opik_enabled: bool
    opik_url_override: str = "http://localhost:5273/api"
    opik_workspace: str = "default"
    opik_project_name: str = "kinsun"


def test_disabled_settings_keep_tracing_off():
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=False))
    assert tracing_client.is_enabled() is False


def test_before_configure_is_disabled():
    tracing_client.reset_for_test()
    assert tracing_client.is_enabled() is False


def test_enabled_settings_export_env_and_turn_on(monkeypatch):
    monkeypatch.delenv("OPIK_URL_OVERRIDE", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)
    monkeypatch.delenv("OPIK_PROJECT_NAME", raising=False)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True))
    import os

    assert tracing_client.is_enabled() is True
    assert os.environ["OPIK_URL_OVERRIDE"] == "http://localhost:5273/api"
    assert os.environ["OPIK_WORKSPACE"] == "default"
    assert os.environ["OPIK_PROJECT_NAME"] == "kinsun"
