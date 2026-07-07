"""format_injected_context 的 golden 測試：釘住排版逐字不回歸。

長期記憶段 → 各事實段（依提供者順序）；每筆記憶帶 provenance／date 註記；
空清單／空事實段一律不產生輸出。
"""

from __future__ import annotations

from kinsun.memory.models import _MEMORY_PREFIX as MEMORY_PREFIX
from kinsun.memory.models import (
    FactSection,
    InjectedContext,
    MemoryItem,
    format_injected_context,
)

_MED_TITLE = "\n這位長者目前固定服用的藥（系統設定的提醒時段，僅供參考、非醫療指示）：\n"
_APPT_TITLE = "\n這位長者即將到來的回診（系統設定，僅供參考）：\n"


def test_format_golden_full():
    injected = InjectedContext(
        memories=[
            MemoryItem("有高血壓", "自述", "2026-07-01"),
            MemoryItem("喜歡爬山"),  # 無 provenance／date → 無註記
        ],
        sections=[
            FactSection(_MED_TITLE, ["血壓藥（早、晚）", "鈣片（睡前）"]),
            FactSection(_APPT_TITLE, ["2026-07-05 心臟科"]),
        ],
    )
    expected = (
        MEMORY_PREFIX
        + "- 有高血壓（自述·2026-07-01）\n- 喜歡爬山\n"
        + _MED_TITLE
        + "- 血壓藥（早、晚）\n- 鈣片（睡前）\n"
        + _APPT_TITLE
        + "- 2026-07-05 心臟科\n"
    )
    assert format_injected_context(injected) == expected


def test_format_memory_annotation_variants():
    injected = InjectedContext(
        memories=[
            MemoryItem("只有來源", "自述"),
            MemoryItem("只有日期", "", "2026-07-01"),
        ]
    )
    assert format_injected_context(injected) == (
        MEMORY_PREFIX + "- 只有來源（自述）\n- 只有日期（2026-07-01）\n"
    )


def test_format_empty_is_empty_string():
    assert format_injected_context(InjectedContext()) == ""
    assert format_injected_context(InjectedContext(sections=[FactSection(_MED_TITLE, [])])) == ""


def test_turn_context_system_suffix_formats_injected():
    from kinsun.memory.models import TurnContext

    ctx = TurnContext(InjectedContext(sections=[FactSection(_MED_TITLE, ["A"])]), history=[])
    assert ctx.system_suffix == _MED_TITLE + "- A\n"
