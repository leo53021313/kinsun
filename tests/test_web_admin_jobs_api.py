from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import Elder, ElderGuardian, Guardian, Role
from kinsun.accounts.service import AccountService
from kinsun.accounts.store import FakeAccountStore
from kinsun.reports.reminders import FakeReminderLogStore
from kinsun.scheduler.scheduler import Job
from kinsun.scheduler.state import FakeScheduleStateStore
from kinsun.schedules.models import (
    Audience,
    CreatedBy,
    RepeatKind,
    Schedule,
    ScheduleKind,
)
from kinsun.schedules.store import FakeScheduleStore
from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers import create_admin_jobs_router

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 12, 12, 0, tzinfo=TPE)


class _FakeRouter:
    """ChannelRouter 替身：記錄送出內容，回報 1 條通道送達。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_text(self, principal_type, principal_id: str, content: str) -> int:
        self.sent.append((principal_type.value, principal_id, content))
        return 1


def _client(
    *,
    internal_testing_enabled: bool = True,
    jobs: list[Job] | None = None,
    accounts: FakeAccountStore | None = None,
    schedule_store: FakeScheduleStore | None = None,
    channel_router: _FakeRouter | None = None,
    reminder_logs: FakeReminderLogStore | None = None,
    schedule_state: FakeScheduleStateStore | None = None,
):
    store = accounts or FakeAccountStore()
    logs = reminder_logs or FakeReminderLogStore()
    app = FastAPI()
    install_error_envelope(app)  # 測試斷言 error.code 需要信封改寫
    app.include_router(
        create_admin_jobs_router(
            admin_api_key="secret",
            internal_testing_enabled=internal_testing_enabled,
            jobs=jobs or [],
            schedule_state=schedule_state or FakeScheduleStateStore(),
            accounts=AccountService(store, clock=lambda: NOW, ttl_hours=24, max_attempts=5),
            schedule_store=schedule_store or FakeScheduleStore(),
            channel_router=channel_router or _FakeRouter(),
            record_reminder=logs.record,
            clock=lambda: NOW,
        ),
        prefix="/api/v1/admin",
    )
    return TestClient(app)


def _auth():
    return {"X-Admin-Key": "secret"}


def test_list_jobs_with_last_run():
    state = FakeScheduleStateStore()
    state.set_last_run("daily-x", NOW)
    jobs = [Job(name="daily-x", cron="0 3 * * *", run=lambda: None)]
    res = _client(jobs=jobs, schedule_state=state).get("/api/v1/admin/jobs", headers=_auth())
    assert res.status_code == 200
    row = res.json()["data"][0]
    assert row["job_name"] == "daily-x"
    assert row["cron"] == "0 3 * * *"
    assert row["last_run_at"] == NOW.timestamp()


# --- 逾期偵測（2026-07-26 全流程模擬實測：排程器活著卻停止運作）---


def test_a_job_that_ran_on_time_is_not_flagged():
    """剛跑過的 job 不該被誤報——時鐘固定在 NOW，上次執行也是 NOW。"""
    state = FakeScheduleStateStore()
    state.set_last_run("daily-x", NOW)
    jobs = [Job(name="daily-x", cron="0 3 * * *", run=lambda: None)]
    body = (
        _client(jobs=jobs, schedule_state=state).get("/api/v1/admin/jobs", headers=_auth()).json()
    )
    assert body["data"][0]["is_overdue"] is False
    assert body["meta"]["overdue"] == []
    assert body["meta"]["warnings"] == []


def test_a_stalled_job_is_flagged_with_a_warning():
    """實測情境：每分鐘該跑的派送停在好幾小時前，程序卻還顯示 RUNNING。

    這一頁本來就有 last_run_at，缺的只是拿它跟 cron 比一下。
    """
    state = FakeScheduleStateStore()
    state.set_last_run("schedule-dispatch", NOW - timedelta(hours=7))
    jobs = [Job(name="schedule-dispatch", cron="* * * * *", run=lambda: None)]
    body = (
        _client(jobs=jobs, schedule_state=state).get("/api/v1/admin/jobs", headers=_auth()).json()
    )
    row = body["data"][0]
    assert row["is_overdue"] is True
    assert row["late_seconds"] > 6 * 3600
    assert body["meta"]["overdue"] == ["schedule-dispatch"]
    assert "逾期未執行" in body["meta"]["warnings"][0]


def test_a_job_that_has_never_run_is_not_flagged():
    """從未跑過的 job（首見種基準前）沒有基準可比，不該報逾期。"""
    jobs = [Job(name="never-ran", cron="* * * * *", run=lambda: None)]
    body = _client(jobs=jobs).get("/api/v1/admin/jobs", headers=_auth()).json()
    assert body["data"][0]["is_overdue"] is False
    assert body["data"][0]["due_at"] is None


def test_list_jobs_requires_admin_key():
    assert _client().get("/api/v1/admin/jobs").status_code == 401


def test_run_job_executes_without_touching_state():
    """spec 2026-07-12 §3.4：手動觸發不寫 scheduler_state，不干擾 worker 到期判斷。"""
    ran: list[str] = []
    state = FakeScheduleStateStore()
    jobs = [Job(name="daily-x", cron="0 3 * * *", run=lambda: ran.append("x"))]
    res = _client(jobs=jobs, schedule_state=state).post(
        "/api/v1/admin/jobs/daily-x/run", headers=_auth()
    )
    assert res.status_code == 200
    assert ran == ["x"]
    assert state.get_last_run("daily-x") is None


def test_run_job_unknown_404():
    res = _client().post("/api/v1/admin/jobs/nope/run", headers=_auth())
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "job_not_found"


def test_run_job_blocked_when_testing_disabled():
    """spec 2026-07-12 §3.4：admin key＋內測開關雙重守門。"""
    jobs = [Job(name="daily-x", cron="0 3 * * *", run=lambda: None)]
    res = _client(internal_testing_enabled=False, jobs=jobs).post(
        "/api/v1/admin/jobs/daily-x/run", headers=_auth()
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "internal_testing_disabled"


def _daily(schedule_id, elder_id, title, kind=ScheduleKind.MEDICATION):
    return Schedule(
        schedule_id=schedule_id,
        group_id=schedule_id,
        elder_id=elder_id,
        kind=kind,
        title=title,
        repeat_kind=RepeatKind.DAILY,
        repeat_time="08:00",
        created_by=CreatedBy.GUARDIAN,
        created_at=1.0,
    )


def test_dispatch_medication_sends_and_records():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    store = FakeScheduleStore()
    store.save(_daily("m1", "e1", "降血壓藥"))
    router = _FakeRouter()
    logs = FakeReminderLogStore()
    res = _client(
        accounts=accounts, schedule_store=store, channel_router=router, reminder_logs=logs
    ).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication"},
        headers=_auth(),
    )
    assert res.status_code == 200
    assert res.json()["data"] == {"kind": "medication", "count": 1}
    assert "降血壓藥" in router.sent[0][2]
    assert logs.recorded[0][1] == "medication"


def test_manual_dispatch_does_not_consume_the_real_reminder():
    """⚠ 手動觸發不可寫 fired_at——否則長輩當天真正該收到的那一則就不會發了。

    這是內測工具，測試動作不可以吃掉正式提醒。
    """
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    store = FakeScheduleStore()
    store.save(_daily("m1", "e1", "降血壓藥"))
    _client(accounts=accounts, schedule_store=store, channel_router=_FakeRouter()).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication"},
        headers=_auth(),
    )
    assert store.get("m1").fired_at is None


def test_dispatch_unknown_kind_422():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    res = _client(accounts=accounts).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "exercise"},
        headers=_auth(),
    )
    assert res.status_code == 422


def test_dispatch_appointment_only_this_elder():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    accounts.save_guardian(Guardian("g1", "小明"))
    accounts.save_elder_guardian(ElderGuardian("e1", "g1", Role.PRIMARY, 1))
    store = FakeScheduleStore()
    mine = _daily("a1", "e1", "心臟科", ScheduleKind.APPOINTMENT)
    store.save(
        Schedule(
            schedule_id="a1",
            group_id="a1",
            elder_id="e1",
            kind=ScheduleKind.APPOINTMENT,
            title="心臟科",
            repeat_kind=RepeatKind.ONCE,
            scheduled_at=NOW.timestamp(),
            event_at=NOW.timestamp(),
            audience=Audience.ELDER_AND_GUARDIAN,
            created_by=CreatedBy.GUARDIAN,
            created_at=1.0,
        )
    )
    store.save(_daily("a2", "e2", "別人的", ScheduleKind.APPOINTMENT))
    assert mine.title == "心臟科"
    router = _FakeRouter()
    res = _client(accounts=accounts, schedule_store=store, channel_router=router).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "appointment"},
        headers=_auth(),
    )
    assert res.json()["data"] == {"kind": "appointment", "count": 1}
    contents = [c for (_, _, c) in router.sent]
    assert any("心臟科" in c for c in contents)
    assert all("別人的" not in c for c in contents)


def test_dispatch_unknown_elder_404():
    res = _client().post(
        "/api/v1/admin/elders/nope/reminders/dispatch",
        json={"kind": "medication"},
        headers=_auth(),
    )
    assert res.status_code == 404


def _enable_hermetic_tracing(monkeypatch):
    """啟用工程觀測但不連 Opik：假 track＝identity、update_current_trace＝no-op。"""
    import opik

    from kinsun.tracing import client as tracing_client

    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik, "track", lambda **kw: lambda f: f)
    monkeypatch.setattr(opik.opik_context, "update_current_trace", lambda **kw: None)


def test_run_job_transparent_when_tracing_enabled(monkeypatch):
    """啟用 Opik 時，admin_run_job 的 root @track 仍須確實執行底層 job。"""
    _enable_hermetic_tracing(monkeypatch)
    ran: list[str] = []
    jobs = [Job(name="daily-x", cron="0 3 * * *", run=lambda: ran.append("x"))]
    res = _client(jobs=jobs).post("/api/v1/admin/jobs/daily-x/run", headers=_auth())
    assert res.status_code == 200
    assert ran == ["x"]


def test_dispatch_reminder_transparent_when_tracing_enabled(monkeypatch):
    """啟用 Opik 時，admin_dispatch_reminder 的 root @track 仍須送出提醒並落帳。"""
    _enable_hermetic_tracing(monkeypatch)
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    store = FakeScheduleStore()
    store.save(_daily("m1", "e1", "降血壓藥"))
    router = _FakeRouter()
    logs = FakeReminderLogStore()
    res = _client(
        accounts=accounts, schedule_store=store, channel_router=router, reminder_logs=logs
    ).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication"},
        headers=_auth(),
    )
    assert res.status_code == 200
    assert "降血壓藥" in router.sent[0][2]
    assert logs.recorded[0][1] == "medication"
