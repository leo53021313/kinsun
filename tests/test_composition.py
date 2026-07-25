"""composition 的離線守門測試：不連 DB、不連網。

刻意檢視 CareAgent／SessionMemory 內部欄位（`_tools`／`_session`／`_facts`）——
這是「組裝形狀」的結構性守門，用來擋掉兩個組裝根再度分岐。
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.accounts.facts import ElderProfileFacts
from kinsun.appointments.facts import AppointmentFacts
from kinsun.composition import Externals, assemble_core, build_tool_registry
from kinsun.config import load_settings
from kinsun.locations.facts import LocationFacts
from kinsun.medications.facts import MedicationFacts
from kinsun.news.store import FakeNewsStore
from kinsun.strategies.facts import StrategyFacts
from kinsun.tools.clock import CURRENT_TIME_SPEC
from kinsun.tools.health_rag import HEALTH_RAG_SPEC
from kinsun.tools.news import NEWS_DETAIL_SPEC, NEWS_SPEC
from kinsun.tools.transport import (
    BUS_ARRIVAL_SPEC,
    MRT_LINE_SPEC,
    PARKING_SPEC,
    ROUTE_SPEC,
)
from kinsun.tools.weather import WEATHER_SPEC
from kinsun.tools.web_search import WEB_SEARCH_SPEC

_ENV = {
    "LINE_CHANNEL_SECRET": "secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "token",
    "GEMINI_API_KEY": "key",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}


def _clock() -> datetime:
    return datetime(2026, 7, 4, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _fake_externals() -> Externals:
    # 組線路階段不呼叫這些外部相依，傳 sentinel 即可（純結構測試）。
    return Externals(db=object(), gemini=object(), long_term=object(), messenger=object())


def _core():
    return assemble_core(load_settings(_ENV), _fake_externals(), clock=_clock)


def test_assemble_core_agent_has_baseline_tools():
    # 無金鑰的預設環境：天氣、時間、衛教 RAG、路線（route 走免金鑰 OSRM，一律註冊）、
    # 最近新聞（get_news 讀自家 news_items 表，免金鑰一律註冊——D-74 後續）。
    # web_search（Tavily）與 TDX 三工具需金鑰，預設環境未設，故不在內。
    core = _core()
    names = {spec.name for spec in core.agent._tools.specs()}
    assert names == {
        WEATHER_SPEC.name,
        CURRENT_TIME_SPEC.name,
        HEALTH_RAG_SPEC.name,
        ROUTE_SPEC.name,
        NEWS_SPEC.name,
        NEWS_DETAIL_SPEC.name,
    }


def test_assemble_core_injects_five_fact_providers_in_order():
    # 順序即 prompt 中的段落順序。稱呼排最前（2026-07-17：模型會亂猜阿公／阿嬤）；
    # LocationFacts 排最後：位置是這幾段裡最不重要的一段。
    core = _core()
    facts = core.agent._session._facts
    assert [type(f) for f in facts] == [
        ElderProfileFacts,
        MedicationFacts,
        AppointmentFacts,
        StrategyFacts,
        LocationFacts,
    ]


def test_build_tool_registry_registers_baseline_tools():
    # 無金鑰：天氣、時間、衛教 RAG、路線 共 4 個（route 免金鑰一律註冊）。
    registry = build_tool_registry(clock=_clock, rag_service=object())
    names = {spec.name for spec in registry.specs()}
    assert names == {
        WEATHER_SPEC.name,
        CURRENT_TIME_SPEC.name,
        HEALTH_RAG_SPEC.name,
        ROUTE_SPEC.name,
    }


def test_build_tool_registry_registers_news_tools_when_store_present():
    # 有給 news store 才註冊 get_news＋get_news_detail；baseline（未給）維持原工具集。
    registry = build_tool_registry(clock=_clock, rag_service=object(), news=FakeNewsStore())
    names = {spec.name for spec in registry.specs()}
    assert {NEWS_SPEC.name, NEWS_DETAIL_SPEC.name} <= names


def test_build_tool_registry_registers_tdx_tools_when_creds_present():
    registry = build_tool_registry(
        clock=_clock, rag_service=object(), tdx_client_id="cid", tdx_client_secret="secret"
    )
    names = {spec.name for spec in registry.specs()}
    assert {BUS_ARRIVAL_SPEC.name, MRT_LINE_SPEC.name, PARKING_SPEC.name} <= names


def test_build_tool_registry_skips_tdx_tools_without_creds():
    # 優雅降級：TDX 憑證未齊時公車／捷運／停車不註冊；路線工具不受影響。
    registry = build_tool_registry(clock=_clock, rag_service=object(), tdx_client_id="cid")
    names = {spec.name for spec in registry.specs()}
    assert not ({BUS_ARRIVAL_SPEC.name, MRT_LINE_SPEC.name, PARKING_SPEC.name} & names)
    assert ROUTE_SPEC.name in names


def test_build_tool_registry_registers_web_search_when_key_present():
    registry = build_tool_registry(clock=_clock, rag_service=object(), tavily_api_key="tvly-key")
    assert WEB_SEARCH_SPEC.name in {spec.name for spec in registry.specs()}


def test_build_tool_registry_skips_web_search_without_key():
    # 優雅降級（spec 2026-07-14）：金鑰未設時金孫少一個工具，其餘功能照常運作。
    registry = build_tool_registry(clock=_clock, rag_service=object(), tavily_api_key="")
    assert WEB_SEARCH_SPEC.name not in {spec.name for spec in registry.specs()}


def test_care_agent_constructed_only_in_composition():
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "kinsun"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "CareAgent(" in path.read_text(encoding="utf-8") and path.name != "composition.py"
    ]
    assert offenders == [], f"CareAgent 只能在 composition.py 建構，違規：{offenders}"


def test_build_externals_configures_tracing(monkeypatch):
    import kinsun.composition as composition
    from kinsun import tracing
    from kinsun.config import load_settings

    configured = {}

    def fake_configure(settings):
        configured["called"] = settings.opik_enabled

    monkeypatch.setattr(tracing, "configure", fake_configure)
    monkeypatch.setattr(tracing, "wrap_genai", lambda c: c)
    monkeypatch.setattr(composition, "ensure_schema", lambda url: None)

    class _FakeDB:
        @staticmethod
        def open(url, max_size):
            return object()

    monkeypatch.setattr(composition, "Database", _FakeDB)
    monkeypatch.setattr(composition, "GeminiClient", lambda **kw: object())
    monkeypatch.setattr(composition, "Mem0LongTermStore", lambda *a, **k: object())
    monkeypatch.setattr(composition, "build_mem0_memory", lambda s: object())
    monkeypatch.setattr(composition, "LineApiMessenger", lambda t: object())

    settings = load_settings(
        {
            "LINE_CHANNEL_SECRET": "s",
            "LINE_CHANNEL_ACCESS_TOKEN": "t",
            "GEMINI_API_KEY": "k",
            "DATABASE_URL": "postgresql://x",
            "OPIK_ENABLED": "false",
        }
    )
    composition.build_externals(settings)
    assert configured["called"] is False
