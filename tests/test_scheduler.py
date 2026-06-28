from datetime import datetime, timedelta, timezone

from kinsun.scheduler.scheduler import Job, Scheduler

TPE = timezone(timedelta(hours=8))


class FakeClock:
    def __init__(self, dt):
        self.dt = dt

    def __call__(self):
        return self.dt


def _job(name, hour, calls):
    return Job(name=name, hour=hour, minute=0, run=lambda: calls.append(name))


def test_runs_when_due():
    calls = []
    clock = FakeClock(datetime(2026, 6, 29, 3, 0, tzinfo=TPE))
    sched = Scheduler([_job("a", 3, calls)], clock)
    assert sched.run_due() == ["a"]
    assert calls == ["a"]


def test_not_due_before_time():
    calls = []
    clock = FakeClock(datetime(2026, 6, 29, 2, 59, tzinfo=TPE))
    sched = Scheduler([_job("a", 3, calls)], clock)
    assert sched.run_due() == []
    assert calls == []


def test_runs_once_per_day():
    calls = []
    clock = FakeClock(datetime(2026, 6, 29, 5, 0, tzinfo=TPE))
    sched = Scheduler([_job("a", 3, calls)], clock)
    sched.run_due()
    assert sched.run_due() == []
    assert calls == ["a"]


def test_runs_again_next_day():
    calls = []
    clock = FakeClock(datetime(2026, 6, 29, 5, 0, tzinfo=TPE))
    sched = Scheduler([_job("a", 3, calls)], clock)
    sched.run_due()
    clock.dt = datetime(2026, 6, 30, 5, 0, tzinfo=TPE)
    assert sched.run_due() == ["a"]
    assert calls == ["a", "a"]


def test_one_job_failure_does_not_block_others():
    calls = []

    def boom():
        raise RuntimeError("boom")

    clock = FakeClock(datetime(2026, 6, 29, 3, 0, tzinfo=TPE))
    sched = Scheduler([Job("boom", 3, 0, boom), _job("ok", 3, calls)], clock)
    assert sched.run_due() == ["boom", "ok"]
    assert calls == ["ok"]
