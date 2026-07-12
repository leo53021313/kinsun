from datetime import datetime, timedelta, timezone

from kinsun.llm import Message
from kinsun.memory.longterm import provenance
from kinsun.memory.longterm.consolidation import run_consolidation
from kinsun.memory.longterm.consolidation_log import FakeConsolidationLogStore
from tests.fakes import FakeLongTermStore, FakeMemoryStore

TPE = timezone(timedelta(hours=8))
NOW_3AM = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)


def _run(elder, short, long_term, *, log=None, now=NOW_3AM):
    return run_consolidation(
        elder,
        short_term=short,
        long_term=long_term,
        log=log or FakeConsolidationLogStore(),
        now=now,
    )


def test_consolidation_writes_previous_day_turns_as_self_claimed():
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "我有高血壓"), at=datetime(2026, 6, 28, 9, 0, tzinfo=TPE))
    long_term = FakeLongTermStore()
    written = _run("sess1", short, long_term)
    assert written == 1
    elder_id, messages, prov = long_term.added[0]
    assert elder_id == "sess1"
    assert prov == provenance.SELF_CLAIMED
    assert messages[0].content == "我有高血壓"


def test_consolidation_archives_complete_days_not_partial_today():
    # 凌晨 3 點批次：要整理 6/28 整天，不能碰 6/29 凌晨剛過的片段（今日尚未結束）。
    short = FakeMemoryStore(now=NOW_3AM)
    yesterday = datetime(2026, 6, 28, 20, 0, tzinfo=TPE)
    early_today = datetime(2026, 6, 29, 1, 0, tzinfo=TPE)
    short.append("sess1", Message("user", "昨天聊的"), at=yesterday)
    short.append("sess1", Message("user", "今天凌晨聊的"), at=early_today)
    long_term = FakeLongTermStore()
    written = _run("sess1", short, long_term)
    assert written == 1
    assert [m.content for m in long_term.added[0][1]] == ["昨天聊的"]


def test_consolidation_skips_when_empty():
    long_term = FakeLongTermStore()
    assert _run("empty", FakeMemoryStore(), long_term) == 0
    assert long_term.added == []


def test_consolidation_backfills_all_missing_days_after_downtime():
    """✅ 庚-06（A-18）：worker 停機跨多日後重啟，中間每個完整日都要各自補整理，不漏天。"""
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "六月26"), at=datetime(2026, 6, 26, 10, 0, tzinfo=TPE))
    short.append("sess1", Message("user", "六月27"), at=datetime(2026, 6, 27, 10, 0, tzinfo=TPE))
    short.append("sess1", Message("user", "六月28"), at=datetime(2026, 6, 28, 10, 0, tzinfo=TPE))
    long_term = FakeLongTermStore()
    written = _run("sess1", short, long_term)
    assert written == 3
    # 三個完整日各自一次寫入（逐日補齊，順序由舊到新）。
    assert [msgs[0].content for _, msgs, _ in long_term.added] == ["六月26", "六月27", "六月28"]


def test_consolidation_is_idempotent_within_same_day():
    """✅ 庚-13（A-19）：同 now 重跑（含 admin 手動觸發）不得重覆寫入長期記憶。"""
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "只此一次"), at=datetime(2026, 6, 28, 9, 0, tzinfo=TPE))
    long_term = FakeLongTermStore()
    log = FakeConsolidationLogStore()
    assert _run("sess1", short, long_term, log=log) == 1
    assert _run("sess1", short, long_term, log=log) == 0  # 已整理 → 不再寫入
    assert len(long_term.added) == 1


def test_consolidation_resumes_only_new_day_next_night():
    """隔夜再跑：已整理的舊日跳過，只補新出現的完整日。"""
    short = FakeMemoryStore(now=NOW_3AM)
    short.append("sess1", Message("user", "六月28"), at=datetime(2026, 6, 28, 10, 0, tzinfo=TPE))
    long_term = FakeLongTermStore()
    log = FakeConsolidationLogStore()
    assert _run("sess1", short, long_term, log=log, now=NOW_3AM) == 1
    # 6/29 又聊了；隔天 6/30 凌晨再跑，只補 6/29，不重跑 6/28。
    short.append("sess1", Message("user", "六月29"), at=datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    next_night = datetime(2026, 6, 30, 3, 0, tzinfo=TPE)
    assert _run("sess1", short, long_term, log=log, now=next_night) == 1
    assert [msgs[0].content for _, msgs, _ in long_term.added] == ["六月28", "六月29"]
