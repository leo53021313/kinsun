"""記憶／情境的結構化資料型別與排版。

刻意只依賴 `llm.Message`，不反向依賴 longterm/recall，以斷開循環匯入：
longterm/store 產出 `MemoryItem`、事實提供者產出 `FactSection`，皆匯入本檔。
所有「排版成 prompt 字串」的邏輯集中在 `format_injected_context`。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kinsun.llm import Message

# 長期記憶段的段首說明（唯一的固定 prefix；事實段的段首由各提供者自帶為 title）。
_MEMORY_PREFIX = (
    "\n以下為這位長者的長期記憶（部分為長者自述、未必經確認，請勿當成醫療診斷）；"
    "已由新到舊排列並附記錄日期。若前後有矛盾，請以較新的記錄為準，"
    "並顧及長者感受、不主動糾正；日期僅供你判斷新舊，回覆時不必提及：\n"
)


@dataclass(frozen=True)
class MemoryItem:
    """一筆長期記憶：文字 ＋ 來源標籤（已解析，如「自述」）＋ 日期（YYYY-MM-DD，缺則空字串）。"""

    text: str
    provenance: str = ""
    date: str = ""


@dataclass(frozen=True)
class FactSection:
    """一段有標題的事實：title 為段首說明（自帶前後換行），items 為各行內容（不含「- 」）。"""

    title: str
    items: list[str]


@dataclass(frozen=True)
class InjectedContext:
    """注入情境：長期記憶清單 ＋ 各事實段。"""

    memories: list[MemoryItem] = field(default_factory=list)
    sections: list[FactSection] = field(default_factory=list)


def _memory_annotation(item: MemoryItem) -> str:
    parts = [p for p in (item.provenance, item.date) if p]
    return f"（{'·'.join(parts)}）" if parts else ""


def _format_memories(memories: list[MemoryItem]) -> str:
    lines = [f"- {m.text}{_memory_annotation(m)}" for m in memories if m.text]
    if not lines:
        return ""
    return _MEMORY_PREFIX + "\n".join(lines) + "\n"


def _format_section(section: FactSection) -> str:
    if not section.items:
        return ""
    return section.title + "\n".join(f"- {item}" for item in section.items) + "\n"


def format_injected_context(injected: InjectedContext) -> str:
    """排版成貼到 system prompt 的字串（順序：長期記憶 → 各事實段，與提供者順序一致）。"""
    out = _format_memories(injected.memories)
    for section in injected.sections:
        out += _format_section(section)
    return out


@dataclass(frozen=True)
class TurnContext:
    """SessionMemory.assemble 的回傳：結構化注入情境 ＋ 今日對話 ＋ 排版後的 prompt 後綴。"""

    injected: InjectedContext
    history: list[Message]

    @property
    def system_suffix(self) -> str:
        return format_injected_context(self.injected)
