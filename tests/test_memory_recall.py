"""SessionMemory：assemble（短期記憶 ＋ 長期記憶 ＋ 事實 → TurnContext）與 record_turn。

排版逐字由 test_memory_models 釘住；本檔專注於「組裝／記錄」行為：哪些記憶／哪些段、
順序、None／失敗段略過、history 帶入、record_turn 逐筆寫入。
"""

import time

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

    def append(self, line_user_id, message, *, at=None):
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


class _SlowFacts:
    """每次查詢固定睡 delay 秒——用來分辨事實提供者是排隊跑還是並行跑。"""

    def __init__(self, section, delay: float) -> None:
        self._section = section
        self._delay = delay

    def facts(self, line_user_id):
        time.sleep(self._delay)
        return self._section


def test_assemble_queries_fact_providers_concurrently():
    """事實提供者必須並行查（2026-07-26 延遲實測）。

    正式組裝有七個（時間／稱呼／三種排程／守則／位置），除時間外各是一次約 0.21 秒的
    Supabase 跨網往返、彼此無依賴，排隊查等於白等約 1.5 秒。
    這裡以「四個各睡 0.1 秒的提供者，總耗時必須明顯少於 0.4 秒」釘住並行性——
    只斷言順序不會發現迴歸（並行版與序列版的輸出一模一樣）。
    """
    delay = 0.1
    providers = [_SlowFacts(FactSection(f"\n第{i}段：\n", [str(i)]), delay) for i in range(4)]

    started = time.monotonic()
    ctx = _session(facts=providers).assemble("s", "x")
    elapsed = time.monotonic() - started

    expected = [f"\n第{i}段：\n" for i in range(len(providers))]
    assert [s.title for s in ctx.injected.sections] == expected
    assert elapsed < delay * len(providers) * 0.75, f"耗時 {elapsed:.2f}s，看起來仍是排隊查"


def test_record_turn_appends_each_message():
    st = _ShortTerm()
    _session(short_term=st).record_turn("u1", Message("user", "嗨"), Message("assistant", "您好"))
    assert st.appended == [
        ("u1", Message("user", "嗨")),
        ("u1", Message("assistant", "您好")),
    ]


def test_gather_facts_spans_carry_injection_index_and_class_name(monkeypatch):
    """七路事實各成一顆 span（2026-07-30 spec）：索引＝注入順序（ScheduleFacts
    註冊三次、純類名會撞名），順序契約不受包裝影響。"""
    import opik

    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    tracing_client.reset_for_test()
    seen: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (seen.append(kw), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    s1 = FactSection("\nA：\n", ["a"])
    s2 = FactSection("\nB：\n", ["b"])
    ctx = _session(facts=[_FakeFacts(s1), _FakeFacts(s2)]).assemble("s", "x")
    assert ctx.injected.sections == [s1, s2]
    names = {kw["name"] for kw in seen}
    assert {"gather_facts", "facts_0__FakeFacts", "facts_1__FakeFacts"} <= names


def test_gather_facts_span_wrapping_keeps_failure_isolation(monkeypatch):
    """包裝後單一提供者失敗仍只略過該段，不中斷對話（既有 fail-safe 不得退化）。"""
    import opik

    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    tracing_client.reset_for_test()
    monkeypatch.setattr(opik, "track", lambda **kw: lambda f: f)
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    section = FactSection("\nA：\n", ["a"])
    ctx = _session(facts=[_BoomFacts(), _FakeFacts(section)]).assemble("s", "x")
    assert ctx.injected.sections == [section]
