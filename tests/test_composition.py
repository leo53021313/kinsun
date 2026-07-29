"""composition 的離線守門測試：不連 DB、不連網。

刻意檢視 CareAgent／SessionMemory 內部欄位（`_tools`／`_session`／`_facts`）——
這是「組裝形狀」的結構性守門，用來擋掉兩個組裝根再度分岐。
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.accounts.facts import ElderProfileFacts
from kinsun.clock import TimeFacts
from kinsun.composition import (
    AUDITED_SPECS,
    Externals,
    assemble_core,
    build_tool_registry,
    list_unregistered_prompt_tools,
)
from kinsun.config import load_settings
from kinsun.locations.facts import LocationFacts
from kinsun.news.store import FakeNewsStore
from kinsun.schedules.facts import ScheduleFacts
from kinsun.schedules.models import ScheduleKind
from kinsun.strategies.facts import StrategyFacts
from kinsun.tools.health_rag import HEALTH_RAG_SPEC
from kinsun.tools.news import NEWS_DETAIL_SPEC, NEWS_SPEC
from kinsun.tools.places import NEARBY_SPEC
from kinsun.tools.schedules import CANCEL_SPEC, CREATE_SPEC, LIST_SPEC
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
    # 無金鑰的預設環境：天氣、衛教 RAG、路線（route 走免金鑰 OSRM，一律註冊）、
    # 最近新聞（get_news 讀自家 news_items 表，免金鑰一律註冊——D-74 後續）。
    # web_search（Tavily）與 TDX 三工具需金鑰，預設環境未設，故不在內。
    # 時間不在工具集（2026-07-25）：已改為每輪注入情境，見下一則測試。
    # 附近地點（spec 2026-07-27）：places／locations 兩個 store 在 assemble_core
    # 一律建構（不像 Tavily／TDX 需要金鑰），故也在無金鑰基線裡。
    core = _core()
    names = {spec.name for spec in core.agent._tools.specs()}
    assert names == {
        WEATHER_SPEC.name,
        HEALTH_RAG_SPEC.name,
        ROUTE_SPEC.name,
        NEWS_SPEC.name,
        NEWS_DETAIL_SPEC.name,
        # 排程三工具（D-76 P4）：長輩用說的建立、查詢與取消提醒。
        CREATE_SPEC.name,
        LIST_SPEC.name,
        CANCEL_SPEC.name,
        NEARBY_SPEC.name,
    }


def test_assemble_core_injects_seven_fact_providers_in_order():
    # 順序即 prompt 中的段落順序。時間排最前（2026-07-25：它是其他事實的座標系，
    # 回診印的是絕對日期）；稱呼緊接其後（2026-07-17：模型會亂猜阿公／阿嬤）；
    # LocationFacts 排最後：位置是這幾段裡最不重要的一段。
    # 統一排程（D-76 P2）把原本的用藥、回診兩段換成三段 ScheduleFacts——位置與
    # 前兩段的標題逐字不變，第三段（長輩自己交代的事）是新增的。
    core = _core()
    facts = core.agent._session._facts
    assert [type(f) for f in facts] == [
        TimeFacts,
        ElderProfileFacts,
        ScheduleFacts,
        ScheduleFacts,
        ScheduleFacts,
        StrategyFacts,
        LocationFacts,
    ]
    assert [f._kind for f in facts if isinstance(f, ScheduleFacts)] == [
        ScheduleKind.MEDICATION,
        ScheduleKind.APPOINTMENT,
        ScheduleKind.CUSTOM,
    ]


def _full_registry():
    """金鑰齊、store 齊的組裝——正式環境該長的樣子。"""
    from kinsun.locations.store import FakeLocationStore
    from kinsun.places.store import FakePlaceStore
    from kinsun.schedules.service import ScheduleService
    from kinsun.schedules.store import FakeScheduleStore

    return build_tool_registry(
        clock=_clock,
        rag_service=object(),
        tavily_api_key="tvly-key",
        tdx_client_id="cid",
        tdx_client_secret="secret",
        news=FakeNewsStore(),
        schedules=ScheduleService(FakeScheduleStore(), clock=_clock),
        places=FakePlaceStore(),
        locations=FakeLocationStore(),
    )


def test_build_tool_registry_registers_baseline_tools():
    # 無金鑰：天氣、衛教 RAG、路線 共 3 個（route 免金鑰一律註冊）。
    registry = build_tool_registry(clock=_clock, rag_service=object())
    names = {spec.name for spec in registry.specs()}
    assert names == {
        WEATHER_SPEC.name,
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


def test_nearby_tool_registered_when_stores_present():
    from kinsun.locations.store import FakeLocationStore
    from kinsun.places.store import FakePlaceStore

    registry = build_tool_registry(
        clock=_clock,
        rag_service=object(),
        places=FakePlaceStore(),
        locations=FakeLocationStore(),
    )
    assert NEARBY_SPEC.name in {spec.name for spec in registry.specs()}


def test_nearby_tool_skipped_without_stores():
    # 優雅降級：沒有 store 就不註冊，其餘工具照常運作。
    registry = build_tool_registry(clock=_clock, rag_service=object())
    assert NEARBY_SPEC.name not in {spec.name for spec in registry.specs()}


# --- 提示詞／註冊表對帳（2026-07-28）---
#
# 提示詞點名了工具、工具卻沒註冊時，模型不會說「我沒有這個工具」，而是假裝呼叫、
# 吐出無限重複的 `tool_code {...}`（2026-07-26 實測單則 186,514 字）。出站護欄
# （`agent._speakable`）擋得住送出去的那一坨，但長輩那一輪還是白問了——真正該做的是
# 讓這種組態在**部署當下**就被看見，而不是等長輩踩到。
#
# ⚠️ 這是警告，不是啟動失敗：優雅降級是刻意的設計（沒有 TDX 憑證仍要能跑）。


def test_unregistered_prompt_tools_flags_web_search_without_key():
    registry = build_tool_registry(clock=_clock, rag_service=object())
    assert WEB_SEARCH_SPEC.name in list_unregistered_prompt_tools(registry)


def test_unregistered_prompt_tools_flags_transport_tools_without_creds():
    """提示詞用「用對應的交通工具查詢」描述、沒有點名，字面掃描掃不到，故須明列。"""
    registry = build_tool_registry(clock=_clock, rag_service=object())
    missing = set(list_unregistered_prompt_tools(registry))
    assert {BUS_ARRIVAL_SPEC.name, MRT_LINE_SPEC.name, PARKING_SPEC.name} <= missing


def test_unregistered_prompt_tools_empty_when_everything_registered():
    """正式組裝（金鑰齊、store 齊）不該有任何缺口，否則這條會紅。"""
    registry = _full_registry()
    assert list_unregistered_prompt_tools(registry) == []


def test_build_tool_registry_warns_about_unregistered_prompt_tools(caplog):
    with caplog.at_level(logging.WARNING, logger="kinsun.composition"):
        build_tool_registry(clock=_clock, rag_service=object())
    warned = "\n".join(record.getMessage() for record in caplog.records)
    assert WEB_SEARCH_SPEC.name in warned


def test_build_tool_registry_stays_quiet_when_nothing_missing(caplog):
    """⚠️ 沒缺口就不可以出聲——每次組裝都噴一行 warning 會讓真的缺口被淹沒。"""
    with caplog.at_level(logging.WARNING, logger="kinsun.composition"):
        _full_registry()
    assert caplog.records == []


def test_prompt_tool_audit_covers_every_tool_spec():
    """防腐化：新增工具卻忘了納入對帳名單時，這條會紅。

    不手寫預期清單——掃 `kinsun.tools` 底下所有模組層級的 ToolSpec，日後加工具自動納入。
    """
    import importlib
    import pkgutil

    import kinsun.tools
    from kinsun.llm import ToolSpec

    defined: set[str] = set()
    for module_info in pkgutil.iter_modules(kinsun.tools.__path__):
        module = importlib.import_module(f"kinsun.tools.{module_info.name}")
        defined |= {v.name for v in vars(module).values() if isinstance(v, ToolSpec)}
    audited = {spec.name for spec in AUDITED_SPECS}
    assert defined <= audited, f"未納入對帳名單的工具：{sorted(defined - audited)}"


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
