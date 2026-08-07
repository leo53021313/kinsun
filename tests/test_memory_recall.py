"""SessionMemory：assemble（短期記憶 ＋ 長期記憶 ＋ 事實 → TurnContext）與 record_turn。

排版逐字由 test_memory_models 釘住；本檔專注於「組裝／記錄」行為：哪些記憶／哪些段、
順序、None／失敗段略過、history 帶入、record_turn 逐筆寫入。
"""

import time

import pytest

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


# ── assemble 三段並行（2026-07-30 延遲優化 A2＋審查 H3／H4）──────────────


class _SlowShortTerm:
    def __init__(self, delay: float) -> None:
        self._delay = delay
        self.appended: list = []

    def recent(self, elder_id):
        time.sleep(self._delay)
        return [Message("user", "早安")]

    def append(self, elder_id, message, *, at=None):
        self.appended.append((elder_id, message))


class _SlowLongTerm:
    def __init__(self, delay: float) -> None:
        self._delay = delay

    def search(self, elder_id, query):
        time.sleep(self._delay)
        return [MemoryItem("記憶內容")]


def test_assemble_runs_its_three_segments_concurrently():
    """今日對話／長期記憶／七路事實三段必須並行（A2）。

    三段各睡 0.15 秒，序列跑就是 0.45 秒；並行後總耗時 ≈ 最慢那一段。
    只斷言輸出不會發現迴歸——並行版與序列版的輸出一模一樣。
    """
    delay = 0.15
    session = SessionMemory(
        _SlowShortTerm(delay),
        _SlowLongTerm(delay),
        facts=[_SlowFacts(FactSection("\n用藥：\n", ["A"]), delay)],
    )

    started = time.monotonic()
    ctx = session.assemble("s", "x")
    elapsed = time.monotonic() - started

    assert ctx.history == [Message("user", "早安")]
    assert ctx.injected.memories == [MemoryItem("記憶內容")]
    assert [s.title for s in ctx.injected.sections] == ["\n用藥：\n"]
    assert elapsed < delay * 3 * 0.75, f"耗時 {elapsed:.2f}s，三段看起來仍是串行"


class _BoomShortTerm:
    def recent(self, elder_id):
        raise RuntimeError("短期記憶讀取失敗")

    def append(self, elder_id, message, *, at=None):  # pragma: no cover
        pass


def test_short_term_failure_surfaces_immediately_without_waiting_for_the_slow_segments():
    """任一段失敗必須立刻冒出來，不可等最慢那段跑完（審查 H3）。

    ⚠️ 這支測試守的是**根因不被改寫**：`with ThreadPoolExecutor(...)` 的 `__exit__`
    是 `shutdown(wait=True)`，例外要等三段都結束才出得來。若最慢那段超過
    `CONTEXT_ASSEMBLY_TIMEOUT_SECONDS`，`PreparedTurn.context()` 的 join 會先到期、
    把真正的根因（短期記憶讀取失敗）改寫成「情境組裝逾時」——下一個人就會往錯的
    方向查。
    """
    slow = 1.0
    session = SessionMemory(
        _BoomShortTerm(),
        _SlowLongTerm(slow),
        facts=[_SlowFacts(FactSection("\n用藥：\n", ["A"]), slow)],
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="短期記憶讀取失敗"):
        session.assemble("s", "x")
    elapsed = time.monotonic() - started

    assert elapsed < slow * 0.5, f"耗時 {elapsed:.2f}s，例外被慢的那幾段擋住了"


def test_a_hanging_fact_provider_is_treated_as_a_missing_section(monkeypatch):
    """單一事實提供者卡住＝該段缺席，不可拖著整輪一起撞 15 秒逾時（審查 H4）。

    沒有這道上限，`PreparedTurn` 逾時放棄後這些執行緒仍握著 psycopg 連線不放，而
    正式環境的池只有 3 條——孤兒會與活著的輪搶連線，形成「逾時→孤兒→更容易逾時」。
    """
    from kinsun.memory import recall as recall_module

    monkeypatch.setattr(recall_module, "_FACT_TIMEOUT_SECONDS", 0.05)
    good = FactSection("\n用藥：\n", ["A"])
    session = _session(
        facts=[_SlowFacts(FactSection("\n卡住的那段：\n", ["X"]), 5.0), _FakeFacts(good)]
    )

    started = time.monotonic()
    ctx = session.assemble("s", "x")
    elapsed = time.monotonic() - started

    assert [s.title for s in ctx.injected.sections] == ["\n用藥：\n"]
    assert elapsed < 1.0, f"耗時 {elapsed:.2f}s，卡住的那段沒有被放棄"


def test_gather_facts_expands_provider_returning_multiple_sections():
    """一個提供者可回多段，展開後仍排在它自己的註冊位置上。

    ScheduleFacts 要用一次查詢供三段（用藥／回診／自訂），故 FactProvider
    的回傳放寬為「單段、多段或缺席」。順序是 prompt 契約：多段要就地展開，
    不可排到所有單段之後。
    """

    class _Multi:
        def facts(self, elder_id):
            return [FactSection("甲", ["a"]), FactSection("乙", ["b"])]

    class _Single:
        def facts(self, elder_id):
            return FactSection("丙", ["c"])

    memory = SessionMemory(_ShortTerm(), FakeLongTermStore(), facts=[_Multi(), _Single()])
    sections = memory._gather_facts("elder-1")
    assert [s.title for s in sections] == ["甲", "乙", "丙"]


def test_gather_facts_provider_returning_empty_list_is_absent():
    """回空清單＝該提供者整段缺席，與回 None 同義（某個 kind 沒排程時的情形）。"""

    class _Empty:
        def facts(self, elder_id):
            return []

    memory = SessionMemory(_ShortTerm(), FakeLongTermStore(), facts=[_Empty()])
    assert memory._gather_facts("elder-1") == []
