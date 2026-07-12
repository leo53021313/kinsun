from datetime import datetime, timedelta, timezone

from kinsun.scheduler.scheduler import Job, Scheduler
from tests.fakes import FakeScheduleStateStore

TPE = timezone(timedelta(hours=8))


class FakeClock:
    def __init__(self, dt):
        self.dt = dt

    def __call__(self):
        return self.dt


def _job(name, cron, calls):
    return Job(name=name, cron=cron, run=lambda: calls.append(name))


def test_first_sight_seeds_and_does_not_fire():
    calls = []
    state = FakeScheduleStateStore()
    clock = FakeClock(datetime(2026, 6, 29, 3, 0, tzinfo=TPE))
    sched = Scheduler([_job("a", "0 3 * * *", calls)], clock, state)
    assert sched.run_due() == []
    assert calls == []
    assert state.get_last_run("a") == clock.dt


def test_fires_after_seed_when_time_passes():
    calls = []
    state = FakeScheduleStateStore()
    clock = FakeClock(datetime(2026, 6, 29, 2, 59, tzinfo=TPE))
    sched = Scheduler([_job("a", "0 3 * * *", calls)], clock, state)
    assert sched.run_due() == []  # 2:59 種基準
    clock.dt = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    assert sched.run_due() == ["a"]
    assert calls == ["a"]


def test_does_not_fire_twice_same_day():
    calls = []
    state = FakeScheduleStateStore()
    clock = FakeClock(datetime(2026, 6, 29, 2, 59, tzinfo=TPE))
    sched = Scheduler([_job("a", "0 3 * * *", calls)], clock, state)
    sched.run_due()  # seed
    clock.dt = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    sched.run_due()  # fire
    clock.dt = datetime(2026, 6, 29, 5, 0, tzinfo=TPE)
    assert sched.run_due() == []
    assert calls == ["a"]


def test_restart_does_not_rerun():
    """核心 bug 修復：新 Scheduler 實例（模擬重啟）+ 同一持久化 state → 不重發。"""
    calls = []
    state = FakeScheduleStateStore()
    clock = FakeClock(datetime(2026, 6, 29, 2, 59, tzinfo=TPE))
    Scheduler([_job("a", "0 3 * * *", calls)], clock, state).run_due()  # seed
    clock.dt = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    Scheduler([_job("a", "0 3 * * *", calls)], clock, state).run_due()  # fire
    clock.dt = datetime(2026, 6, 29, 4, 0, tzinfo=TPE)
    assert Scheduler([_job("a", "0 3 * * *", calls)], clock, state).run_due() == []
    assert calls == ["a"]


def test_catch_up_once_after_downtime():
    calls = []
    state = FakeScheduleStateStore()
    state.set_last_run("a", datetime(2026, 6, 28, 3, 0, tzinfo=TPE))  # 昨日跑過
    clock = FakeClock(datetime(2026, 6, 29, 9, 0, tzinfo=TPE))  # 今日 9:00（跨過今日 3:00）
    sched = Scheduler([_job("a", "0 3 * * *", calls)], clock, state)
    assert sched.run_due() == ["a"]  # 補跑一次
    assert sched.run_due() == []  # 立刻快進、不再補
    assert calls == ["a"]


def test_full_cron_every_five_minutes():
    calls = []
    state = FakeScheduleStateStore()
    state.set_last_run("a", datetime(2026, 6, 29, 10, 0, tzinfo=TPE))
    clock = FakeClock(datetime(2026, 6, 29, 10, 4, tzinfo=TPE))
    sched = Scheduler([_job("a", "*/5 * * * *", calls)], clock, state)
    assert sched.run_due() == []  # 10:04，下次 10:05 未到
    clock.dt = datetime(2026, 6, 29, 10, 5, tzinfo=TPE)
    assert sched.run_due() == ["a"]


def test_one_job_failure_does_not_block_others():
    calls = []
    state = FakeScheduleStateStore()
    state.set_last_run("boom", datetime(2026, 6, 28, 3, 0, tzinfo=TPE))
    state.set_last_run("ok", datetime(2026, 6, 28, 3, 0, tzinfo=TPE))

    def boom():
        raise RuntimeError("boom")

    clock = FakeClock(datetime(2026, 6, 29, 3, 0, tzinfo=TPE))
    sched = Scheduler(
        [Job("boom", "0 3 * * *", boom), _job("ok", "0 3 * * *", calls)], clock, state
    )
    assert sched.run_due() == ["boom", "ok"]
    assert calls == ["ok"]
    assert state.get_last_run("boom") == clock.dt  # 失敗仍標記


def test_two_workers_shared_state_run_job_once():
    """✅ 庚-17（A-42）：誤起雙 worker（共用同一狀態表）時，同一到期 job
    只有搶到的那個執行——長輩不再收到雙重提醒。

    模擬最壞交錯：w1 正在跑 job（尚未寫回狀態的舊實作窗口），w2 同時
    醒來檢查同一 job。修復後 w1 於執行前先原子搶占，w2 看到的已是新
    狀態 → 不再重跑。"""
    runs = []
    state = FakeScheduleStateStore()
    seed = datetime(2026, 7, 12, 7, 0, tzinfo=TPE)
    now = datetime(2026, 7, 12, 8, 0, tzinfo=TPE)
    holder = {}

    def w1_run():
        runs.append("w1")
        holder["w2"].run_due()  # w1 執行中，w2 的 tick 同時發生

    w1 = Scheduler([Job("greet", "0 8 * * *", w1_run)], clock=lambda: now, state=state)
    w2 = Scheduler(
        [Job("greet", "0 8 * * *", lambda: runs.append("w2"))], clock=lambda: now, state=state
    )
    holder["w2"] = w2
    state.set_last_run("greet", seed)
    w1.run_due()
    assert runs == ["w1"]
