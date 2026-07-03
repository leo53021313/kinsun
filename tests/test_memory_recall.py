from kinsun.memory.recall import MemoryContext
from tests.fakes import FakeLongTermStore


def test_recall_delegates_to_longterm_search():
    ctx = MemoryContext(FakeLongTermStore(search_result="記憶內容"))
    assert ctx.recall("sess1", "今天好嗎") == "記憶內容"


def test_recall_empty_when_no_memory():
    assert MemoryContext(FakeLongTermStore()).recall("sess1", "x") == ""


class _FakeFacts:
    def __init__(self, text):
        self._text = text

    def facts(self, line_user_id):
        return self._text


def test_recall_appends_fact_providers():
    ctx = MemoryContext(
        FakeLongTermStore(search_result="長期記憶內容\n"),
        facts=[_FakeFacts("用藥A\n"), _FakeFacts("用藥B\n")],
    )
    out = ctx.recall("sess1", "今天好嗎")
    assert out == "長期記憶內容\n用藥A\n用藥B\n"


def test_recall_no_facts_is_just_longterm():
    ctx = MemoryContext(FakeLongTermStore(search_result="只有長期記憶"))
    assert ctx.recall("sess1", "x") == "只有長期記憶"


class _BoomFacts:
    def facts(self, line_user_id):
        raise RuntimeError("db down")


def test_recall_skips_failing_fact_provider():
    ctx = MemoryContext(
        FakeLongTermStore(search_result="長期\n"),
        facts=[_BoomFacts(), _FakeFacts("用藥A\n")],
    )
    assert ctx.recall("s", "x") == "長期\n用藥A\n"
