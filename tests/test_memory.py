from datetime import datetime, timedelta, timezone

from kinsun.llm import Message
from kinsun.memory.store import SqliteMemoryStore

TPE = timezone(timedelta(hours=8))


class FakeClock:
    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


def _store(dt: datetime, max_turns: int = 20) -> SqliteMemoryStore:
    return SqliteMemoryStore(":memory:", FakeClock(dt), max_turns)


def test_recent_empty_for_new_session():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    assert store.recent("u1") == []


def test_append_then_recent_in_order():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    store.append("u1", Message("user", "早安"))
    store.append("u1", Message("assistant", "阿公早"))
    assert store.recent("u1") == [Message("user", "早安"), Message("assistant", "阿公早")]


def test_sessions_isolated():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    store.append("u1", Message("user", "A"))
    store.append("u2", Message("user", "B"))
    assert store.recent("u1") == [Message("user", "A")]


def test_yesterday_excluded():
    clock = FakeClock(datetime(2026, 6, 28, 23, 0, tzinfo=TPE))
    store = SqliteMemoryStore(":memory:", clock, 20)
    store.append("u1", Message("user", "昨天"))
    clock.dt = datetime(2026, 6, 29, 8, 0, tzinfo=TPE)
    store.append("u1", Message("user", "今天"))
    assert store.recent("u1") == [Message("user", "今天")]


def test_caps_to_max_turns():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE), max_turns=2)
    for i in range(5):
        store.append("u1", Message("user", str(i)))
    assert store.recent("u1") == [Message("user", "3"), Message("user", "4")]


def test_sessions_lists_distinct_sorted():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    store.append("u2", Message("user", "B"))
    store.append("u1", Message("user", "A"))
    store.append("u1", Message("assistant", "a"))
    assert store.sessions() == ["u1", "u2"]


def test_sessions_empty():
    store = _store(datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    assert store.sessions() == []
