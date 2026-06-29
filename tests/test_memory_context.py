from kinsun.recall import MemoryContext
from tests.fakes import FakeLongTermStore


def test_recall_delegates_to_longterm_search():
    ctx = MemoryContext(FakeLongTermStore(search_result="記憶內容"))
    assert ctx.recall("sess1", "今天好嗎") == "記憶內容"


def test_recall_empty_when_no_memory():
    assert MemoryContext(FakeLongTermStore()).recall("sess1", "x") == ""
