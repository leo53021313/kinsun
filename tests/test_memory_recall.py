"""SessionMemory：assemble（短期記憶 ＋ 長期記憶 ＋ 事實 → TurnContext）與 record_turn。

排版逐字由 test_memory_models 釘住；本檔專注於「組裝／記錄」行為：哪些記憶／哪些段、
順序、None／失敗段略過、history 帶入、record_turn 逐筆寫入。
"""

from kinsun.llm import Message
from kinsun.memory.models import FactSection, InjectedContext, MemoryItem
from kinsun.memory.recall import SessionMemory
from tests.fakes import FakeLongTermStore


class _ShortTerm:
    def __init__(self, history=None):
        self._history = history or []
        self.appended = []

    def recent(self, line_user_id):
        return list(self._history)

    def append(self, line_user_id, message):
        self.appended.append((line_user_id, message))


class _FakeFacts:
    def __init__(self, section):
        self._section = section

    def facts(self, line_user_id):
        return self._section


class _BoomFacts:
    def facts(self, line_user_id):
        raise RuntimeError("db down")


def _session(short_term=None, memories=None, facts=None):
    return SessionMemory(
        short_term or _ShortTerm(), FakeLongTermStore(memories=memories), facts=facts
    )


def test_assemble_includes_memories_and_history():
    mem = MemoryItem("記憶內容")
    st = _ShortTerm([Message("user", "早安")])
    ctx = _session(short_term=st, memories=[mem]).assemble("sess1", "今天好嗎")
    assert ctx.injected == InjectedContext(memories=[mem])
    assert ctx.history == [Message("user", "早安")]


def test_assemble_sections_in_order_omitting_none():
    s1 = FactSection("\n用藥：\n", ["A"])
    s2 = FactSection("\n回診：\n", ["B"])
    ctx = _session(facts=[_FakeFacts(s1), _FakeFacts(None), _FakeFacts(s2)]).assemble("s", "x")
    assert ctx.injected.sections == [s1, s2]


def test_assemble_skips_failing_fact_provider():
    s1 = FactSection("\n用藥：\n", ["A"])
    ctx = _session(facts=[_BoomFacts(), _FakeFacts(s1)]).assemble("s", "x")
    assert ctx.injected.sections == [s1]


def test_record_turn_appends_each_message():
    st = _ShortTerm()
    _session(short_term=st).record_turn("u1", Message("user", "嗨"), Message("assistant", "您好"))
    assert st.appended == [
        ("u1", Message("user", "嗨")),
        ("u1", Message("assistant", "您好")),
    ]
