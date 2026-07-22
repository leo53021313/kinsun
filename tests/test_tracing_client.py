from dataclasses import dataclass

from kinsun.tracing import client as tracing_client


@dataclass
class _S:
    opik_enabled: bool
    opik_url_override: str = "http://localhost:5273/api"
    opik_workspace: str = "default"
    opik_project_name: str = "kinsun"
    opik_ping_timeout_seconds: float = 2.0


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
    # 可達＝啟用；用 monkeypatch 取代真實探測，測試不必起 Opik 服務。
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", lambda *_a, **_k: True)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True))
    import os

    assert tracing_client.is_enabled() is True
    assert os.environ["OPIK_URL_OVERRIDE"] == "http://localhost:5273/api"
    assert os.environ["OPIK_WORKSPACE"] == "default"
    assert os.environ["OPIK_PROJECT_NAME"] == "kinsun"


def test_enabled_but_unreachable_degrades_to_off(monkeypatch):
    # OPIK_ENABLED=true 但服務連不到：安靜降級為 no-op，且不匯出環境變數。
    monkeypatch.delenv("OPIK_URL_OVERRIDE", raising=False)
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", lambda *_a, **_k: False)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True))
    import os

    assert tracing_client.is_enabled() is False
    assert os.environ.get("OPIK_URL_OVERRIDE") is None


def test_reachability_probe_swallows_network_errors():
    # 探測本身遇到任何錯誤都回 False，不得往外拋（連不到的位址）。
    assert tracing_client._is_opik_reachable("http://127.0.0.1:1/api", timeout=0.2) is False
