import threading
import time
from datetime import datetime, timedelta, timezone

from kinsun.cron.scheduler import Job, Scheduler
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


# --- 長跑 job 不佔住掃描迴圈（2026-07-26 實測：夜間批次卡住每分鐘的提醒派送）---


def test_a_long_background_job_does_not_block_the_rest_of_the_tick():
    """背景 job 只負責啟動就回來，後面的 job 照跑。

    ⚠️ 這條守的是長輩的吃藥提醒：`run_due` 原本逐一同步執行，`daily-consolidation`
    對 39 位長輩跑整理＋摘要＋反思時，每分鐘該派送的 `schedule-dispatch` 整整兩分鐘
    沒有動（2026-07-26 實測）。長輩人數再多一些，提醒就會遲到十幾分鐘。
    """
    started = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def _slow() -> None:
        order.append("slow-start")
        started.set()
        release.wait(timeout=30)
        order.append("slow-end")

    state = FakeScheduleStateStore()
    seed = datetime(2026, 7, 12, 7, 0, tzinfo=TPE)
    now = datetime(2026, 7, 12, 8, 0, tzinfo=TPE)
    for name in ("slow", "fast"):
        state.set_last_run(name, seed)
    sched = Scheduler(
        [
            Job("slow", "0 8 * * *", _slow, background=True),
            Job("fast", "0 8 * * *", lambda: order.append("fast")),
        ],
        clock=lambda: now,
        state=state,
    )
    assert sched.run_due() == ["slow", "fast"]
    assert started.wait(timeout=30), "背景 job 沒有被啟動"
    assert "fast" in order, "掃描迴圈被慢 job 卡住了——這正是事故當晚的情形"
    assert "slow-end" not in order, "run_due 等了背景 job 跑完，等於沒有背景化"
    release.set()


def test_a_background_job_still_running_is_not_started_again():
    """上一輪還沒跑完就不再啟動，也**不認領**。

    認領會把 last_run_at 推到現在＝謊稱「這一輪跑過了」；真正該表達的是
    「這一輪不必再跑，因為上一輪還沒結束」。夜間批次跑超過一個掃描間隔是常態
    （逐位長輩呼叫 LLM），沒有這道防護會疊出好幾份同時在寫同一位長輩的記憶。
    """
    release = threading.Event()
    runs: list[int] = []

    def _slow() -> None:
        runs.append(1)
        release.wait(timeout=30)

    state = FakeScheduleStateStore()
    seed = datetime(2026, 7, 12, 7, 0, tzinfo=TPE)
    now = datetime(2026, 7, 12, 8, 0, tzinfo=TPE)
    state.set_last_run("slow", seed)
    sched = Scheduler(
        [Job("slow", "0 8 * * *", _slow, background=True)], clock=lambda: now, state=state
    )
    assert sched.run_due() == ["slow"]
    claimed_at = state.get_last_run("slow")
    assert sched.run_due() == [], "上一輪還在跑，不該再啟動一份"
    assert state.get_last_run("slow") == claimed_at, "跳過的這一輪不該改動 last_run_at"
    assert len(runs) == 1
    release.set()


def test_a_crashing_background_job_does_not_kill_the_scheduler():
    """背景 job 拋例外只留 exception log，掃描迴圈照走——與同步 job 同語意。"""
    boom = threading.Event()

    def _boom() -> None:
        boom.set()
        raise RuntimeError("背景炸了")

    state = FakeScheduleStateStore()
    seed = datetime(2026, 7, 12, 7, 0, tzinfo=TPE)
    now = datetime(2026, 7, 12, 8, 0, tzinfo=TPE)
    state.set_last_run("boom", seed)
    sched = Scheduler(
        [Job("boom", "0 8 * * *", _boom, background=True)], clock=lambda: now, state=state
    )
    assert sched.run_due() == ["boom"]
    assert boom.wait(timeout=30)
    # 例外被吞在背景執行緒裡；下一輪（狀態已推進）自然不再到期。
    assert sched.run_due() == []


def test_a_background_job_stuck_too_long_escalates_to_a_warning(caplog, monkeypatch):
    """卡住的背景 job 必須叫出來，不能只留一行 INFO。

    ⚠️ 這是背景化製造出的新盲點：背景 job 若永遠不結束，掃描迴圈照跑、心跳照更新、
    看門狗看不出異常（它守的是 tick 有沒有推進），而這支 job 每一輪都被跳過、
    再也不會執行——系統看起來很健康，某個功能已經死了。那正是 2026-07-26
    停擺事故的形狀，不可以在修它的過程中又造一個。
    """
    import logging as _logging

    release = threading.Event()
    state = FakeScheduleStateStore()
    seed = datetime(2026, 7, 12, 7, 0, tzinfo=TPE)
    now = datetime(2026, 7, 12, 8, 0, tzinfo=TPE)
    state.set_last_run("slow", seed)
    sched = Scheduler(
        [Job("slow", "0 8 * * *", lambda: release.wait(timeout=30), background=True)],
        clock=lambda: now,
        state=state,
    )
    sched.run_due()
    # 假裝它已經跑了兩小時（門檻 1 小時）
    thread, _started = sched._inflight["slow"]
    sched._inflight["slow"] = (thread, time.monotonic() - 7200)
    with caplog.at_level(_logging.WARNING):
        sched.run_due()
        sched.run_due()  # 第二輪不該再刷一次，否則日誌會被洗掉
    warnings = [r for r in caplog.records if r.levelno >= _logging.WARNING]
    assert len(warnings) == 1, "卡住要叫、但只叫一次"
    assert "可能卡住" in warnings[0].getMessage()
    release.set()


# ── 成功訊號（2026-07-27）──
#
# `last_run_at` 寫的是「認領」不是「成功」（見 _claim_if_due），所以「每輪都認領成功、
# 每輪都拋例外」的 job 在後台一律顯示健康。加獨立的成功訊號才分得開。


def test_success_is_recorded_only_when_the_job_actually_finishes():
    state = FakeScheduleStateStore()
    state.set_last_run("boom", datetime(2026, 7, 26, 3, 0, tzinfo=TPE))
    state.set_last_run("ok", datetime(2026, 7, 26, 3, 0, tzinfo=TPE))

    def boom():
        raise RuntimeError("boom")

    clock = FakeClock(datetime(2026, 7, 27, 3, 0, tzinfo=TPE))
    sched = Scheduler(
        [Job("boom", "0 3 * * *", boom), Job("ok", "0 3 * * *", lambda: None)], clock, state
    )

    sched.run_due()

    # 兩支都被認領（at-most-once 語意不變，庚-17／A-42）
    assert state.get_last_run("boom") == clock.dt
    assert state.get_last_run("ok") == clock.dt
    # 但只有真的跑完的那支留下成功訊號——這正是後台分得出「持續失敗」的依據
    assert state.get_last_success("boom") is None
    assert state.get_last_success("ok") == clock.dt


def test_recording_success_failure_does_not_break_the_scheduler():
    """成功訊號是觀測用的，寫不進去不可反過來弄壞排程。"""

    class _BoomOnSuccess(FakeScheduleStateStore):
        def record_success(self, job_name, when):
            raise RuntimeError("db down")

    state = _BoomOnSuccess()
    state.set_last_run("ok", datetime(2026, 7, 26, 3, 0, tzinfo=TPE))
    ran = []
    clock = FakeClock(datetime(2026, 7, 27, 3, 0, tzinfo=TPE))
    sched = Scheduler([Job("ok", "0 3 * * *", lambda: ran.append(1))], clock, state)

    assert sched.run_due() == ["ok"]
    assert ran == [1]
