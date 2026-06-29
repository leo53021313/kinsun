from kinsun.llm import Message
from kinsun.longterm import provenance
from kinsun.longterm.consolidation import run_consolidation
from tests.fakes import FakeLongTermStore, FakeMemoryStore


def test_consolidation_writes_today_turns_as_self_claimed():
    short = FakeMemoryStore()
    short.append("sess1", Message("user", "我有高血壓"))
    long_term = FakeLongTermStore()
    written = run_consolidation("sess1", short_term=short, long_term=long_term)
    assert written == 1
    session_id, messages, prov = long_term.added[0]
    assert session_id == "sess1"
    assert prov == provenance.SELF_CLAIMED
    assert messages[0].text == "我有高血壓"


def test_consolidation_skips_when_empty():
    long_term = FakeLongTermStore()
    assert run_consolidation("empty", short_term=FakeMemoryStore(), long_term=long_term) == 0
    assert long_term.added == []
