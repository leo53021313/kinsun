"""composition 的離線守門測試：不連 DB、不連網。

刻意檢視 CareAgent／MemoryContext 內部欄位（`_tools`／`_context`／`_facts`）——
這是「組裝形狀」的結構性守門，用來擋掉兩個組裝根再度分岐。
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.appointments.facts import AppointmentFacts
from kinsun.composition import Externals, assemble_core, build_tool_registry
from kinsun.config import load_settings
from kinsun.medications.facts import MedicationFacts
from kinsun.tools.clock import CURRENT_TIME_SPEC
from kinsun.tools.health_rag import HEALTH_RAG_SPEC
from kinsun.tools.weather import WEATHER_SPEC

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


def test_assemble_core_agent_has_all_three_tools():
    core = _core()
    names = {spec.name for spec in core.agent._tools.specs()}
    assert names == {WEATHER_SPEC.name, CURRENT_TIME_SPEC.name, HEALTH_RAG_SPEC.name}


def test_assemble_core_injects_two_fact_providers_in_order():
    core = _core()
    facts = core.agent._context._facts
    assert [type(f) for f in facts] == [MedicationFacts, AppointmentFacts]


def test_build_tool_registry_registers_three_tools():
    registry = build_tool_registry(clock=_clock, rag_service=object())
    assert len(registry.specs()) == 3


def test_care_agent_constructed_only_in_composition():
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "kinsun"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "CareAgent(" in path.read_text(encoding="utf-8") and path.name != "composition.py"
    ]
    assert offenders == [], f"CareAgent 只能在 composition.py 建構，違規：{offenders}"
