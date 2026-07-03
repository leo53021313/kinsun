from datetime import datetime, timedelta, timezone

from tests.fakes import FakeScheduleStateStore

TPE = timezone(timedelta(hours=8))


def test_fake_returns_none_when_unset():
    store = FakeScheduleStateStore()
    assert store.get_last_run("a") is None


def test_fake_round_trip():
    store = FakeScheduleStateStore()
    when = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    store.set_last_run("a", when)
    assert store.get_last_run("a") == when
