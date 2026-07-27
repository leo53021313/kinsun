import os
from dataclasses import dataclass

from kinsun.tracing import client as tracing_client


@dataclass
class _S:
    opik_enabled: bool
    opik_url_override: str = "http://localhost:5273/api"
    opik_workspace: str = "default"
    opik_project_name: str = "kinsun"
    opik_ping_timeout_seconds: float = 2.0
    opik_reprobe_interval_seconds: float = 60.0


class _FakeClock:
    """可控的單調時鐘：測重探間隔不必真的等 60 秒。"""

    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _CountingProbe:
    """記錄探測次數的假探測；`reachable` 可隨時改，模擬 Opik 中途起來。"""

    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable
        self.calls = 0

    def __call__(self, *_args, **_kwargs) -> bool:
        self.calls += 1
        return self.reachable


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

    assert tracing_client.is_enabled() is False
    assert os.environ.get("OPIK_URL_OVERRIDE") is None


def test_reachability_probe_swallows_network_errors():
    # 探測本身遇到任何錯誤都回 False，不得往外拋（連不到的位址）。
    assert tracing_client._is_opik_reachable("http://127.0.0.1:1/api", timeout=0.2) is False


def test_unreachable_at_startup_recovers_after_reprobe_interval(monkeypatch):
    """啟動時連不到不再是終身判決：間隔到了且服務已起來，就自己接回去。

    ⚠️ 這是 2026-07-27 的回歸測試，對應一個真的發生過的事故：kinsun.sh 全套 restart
    時 opik 第一個停、最後一個起（冷啟 30–60 秒），webhook 卻在自己啟動後 2 秒就探測
    完並永久放棄，於是那個行程整段壽命的長輩對話一筆都沒進 Opik——而 Opik 明明在
    一分鐘後就活著了。
    """
    monkeypatch.delenv("OPIK_URL_OVERRIDE", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)
    monkeypatch.delenv("OPIK_PROJECT_NAME", raising=False)
    clock = _FakeClock()
    probe = _CountingProbe(reachable=False)
    monkeypatch.setattr(tracing_client, "_now", clock)
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", probe)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True, opik_reprobe_interval_seconds=60.0))

    assert tracing_client.is_enabled() is False
    assert probe.calls == 1

    # 間隔未到：不得重探——is_enabled() 在每個 track／tag 上被呼叫，不能每次都碰網路。
    clock.advance(59.0)
    assert tracing_client.is_enabled() is False
    assert probe.calls == 1

    # 間隔到了、Opik 也起來了：自己接回去，並補上 SDK 需要的環境變數。
    probe.reachable = True
    clock.advance(1.0)
    assert tracing_client.is_enabled() is True
    assert probe.calls == 2
    assert os.environ["OPIK_URL_OVERRIDE"] == "http://localhost:5273/api"
    assert os.environ["OPIK_WORKSPACE"] == "default"
    assert os.environ["OPIK_PROJECT_NAME"] == "kinsun"


def test_failed_reprobe_restarts_the_interval(monkeypatch):
    """重探仍失敗：間隔重新起算，不會退化成「每次呼叫都探一次」。"""
    clock = _FakeClock()
    probe = _CountingProbe(reachable=False)
    monkeypatch.setattr(tracing_client, "_now", clock)
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", probe)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True, opik_reprobe_interval_seconds=60.0))
    assert probe.calls == 1

    clock.advance(60.0)
    assert tracing_client.is_enabled() is False
    assert probe.calls == 2

    # 緊接著連呼叫多次都不該再探；要再等滿一個間隔。
    assert tracing_client.is_enabled() is False
    assert tracing_client.is_enabled() is False
    assert probe.calls == 2

    clock.advance(60.0)
    assert tracing_client.is_enabled() is False
    assert probe.calls == 3


def test_enabled_state_never_reprobes(monkeypatch):
    """已啟用後不得再碰網路：is_enabled() 是對話熱路徑上每個 span 都會走的判斷。"""
    monkeypatch.setattr(tracing_client, "_now", _FakeClock())
    probe = _CountingProbe(reachable=True)
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", probe)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=True))
    assert probe.calls == 1

    for _ in range(5):
        assert tracing_client.is_enabled() is True
    assert probe.calls == 1


def test_disabled_settings_never_probe(monkeypatch):
    """OPIK_ENABLED=false 是明確的關閉，連一次探測都不該做（開發機／CI 常態）。"""
    clock = _FakeClock()
    probe = _CountingProbe(reachable=True)
    monkeypatch.setattr(tracing_client, "_now", clock)
    monkeypatch.setattr(tracing_client, "_is_opik_reachable", probe)
    tracing_client.reset_for_test()
    tracing_client.configure(_S(opik_enabled=False))

    clock.advance(3600.0)
    assert tracing_client.is_enabled() is False
    assert probe.calls == 0
