from datetime import datetime, timedelta, timezone

from kinsun.llm import Message
from kinsun.memory.longterm import provenance
from kinsun.memory.longterm.consolidation import run_consolidation
from tests.fakes import FakeLongTermStore, FakeMemoryStore

TPE = timezone(timedelta(hours=8))
NOW_3AM = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)


def test_consolidation_writes_previous_day_turns_as_self_claimed():
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "我有高血壓"), at=datetime(2026, 6, 28, 9, 0, tzinfo=TPE))
    long_term = FakeLongTermStore()
    written = run_consolidation("sess1", short_term=short, long_term=long_term)
    assert written == 1
    session_id, messages, prov = long_term.added[0]
    assert session_id == "sess1"
    assert prov == provenance.SELF_CLAIMED
    assert messages[0].text == "我有高血壓"


def test_consolidation_archives_previous_day_not_partial_today():
    # 凌晨 3 點批次：要整理 6/28 整天，不能只抓到 6/29 凌晨剛過的片段。
    yesterday = datetime(2026, 6, 28, 20, 0, tzinfo=TPE)
    early_today = datetime(2026, 6, 29, 1, 0, tzinfo=TPE)
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "昨天聊的"), at=yesterday)
    short.append("sess1", Message("user", "今天凌晨聊的"), at=early_today)
    long_term = FakeLongTermStore()
    written = run_consolidation("sess1", short_term=short, long_term=long_term)
    assert written == 1
    _, messages, _ = long_term.added[0]
    assert [m.text for m in messages] == ["昨天聊的"]


def test_consolidation_skips_when_empty():
    long_term = FakeLongTermStore()
    assert run_consolidation("empty", short_term=FakeMemoryStore(), long_term=long_term) == 0
    assert long_term.added == []
