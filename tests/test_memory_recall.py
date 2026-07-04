"""MemoryContext.recall：組裝長期記憶 ＋ 各事實段 → 排版字串。

recall 的字串輸出以 format_injected_context 對照（排版逐字由 test_memory_models 釘住），
本檔專注於「組裝」行為：哪些記憶／哪些段、順序、None／失敗段的略過。
"""

from kinsun.memory.models import FactSection, InjectedContext, MemoryItem, format_injected_context
from kinsun.memory.recall import MemoryContext
from tests.fakes import FakeLongTermStore


class _FakeFacts:
    def __init__(self, section):
        self._section = section

    def facts(self, line_user_id):
        return self._section


class _BoomFacts:
    def facts(self, line_user_id):
        raise RuntimeError("db down")


def test_recall_includes_longterm_memories():
    mem = MemoryItem("記憶內容")
    ctx = MemoryContext(FakeLongTermStore(memories=[mem]))
    assert ctx.recall("sess1", "今天好嗎") == format_injected_context(
        InjectedContext(memories=[mem])
    )


def test_recall_empty_when_no_memory_no_facts():
    assert MemoryContext(FakeLongTermStore()).recall("sess1", "x") == ""


def test_recall_assembles_memories_then_sections_in_order():
    mem = MemoryItem("長期A")
    s1 = FactSection("\n用藥：\n", ["A"])
    s2 = FactSection("\n回診：\n", ["B"])
    ctx = MemoryContext(FakeLongTermStore(memories=[mem]), facts=[_FakeFacts(s1), _FakeFacts(s2)])
    assert ctx.recall("sess1", "x") == format_injected_context(
        InjectedContext(memories=[mem], sections=[s1, s2])
    )


def test_recall_omits_none_sections():
    s1 = FactSection("\n用藥：\n", ["A"])
    ctx = MemoryContext(FakeLongTermStore(), facts=[_FakeFacts(None), _FakeFacts(s1)])
    assert ctx.recall("s", "x") == format_injected_context(InjectedContext(sections=[s1]))


def test_recall_skips_failing_fact_provider():
    s1 = FactSection("\n用藥：\n", ["A"])
    ctx = MemoryContext(FakeLongTermStore(), facts=[_BoomFacts(), _FakeFacts(s1)])
    assert ctx.recall("s", "x") == format_injected_context(InjectedContext(sections=[s1]))
