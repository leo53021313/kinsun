from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import Elder, ElderGuardian, Guardian, Role
from kinsun.accounts.service import AccountService
from kinsun.accounts.store import FakeAccountStore
from kinsun.appointments.models import Appointment
from kinsun.appointments.store import FakeAppointmentStore
from kinsun.medications.models import Medication, MedicationSlot
from kinsun.medications.store import FakeMedicationStore
from kinsun.reports.reminders import FakeReminderLogStore
from kinsun.scheduler.scheduler import Job
from kinsun.scheduler.state import FakeScheduleStateStore
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
    med_store: FakeMedicationStore | None = None,
    appt_store: FakeAppointmentStore | None = None,
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
            med_store=med_store or FakeMedicationStore(),
            appt_store=appt_store or FakeAppointmentStore(),
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
    assert res.json()["data"] == [
        {"job_name": "daily-x", "cron": "0 3 * * *", "last_run_at": NOW.timestamp()}
    ]


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


def test_dispatch_medication_sends_and_records():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    meds = FakeMedicationStore()
    meds.save(Medication("m1", "e1", "降血壓藥", (MedicationSlot.MORNING,)))
    router = _FakeRouter()
    logs = FakeReminderLogStore()
    res = _client(
        accounts=accounts, med_store=meds, channel_router=router, reminder_logs=logs
    ).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication", "slot": "morning"},
        headers=_auth(),
    )
    assert res.status_code == 200
    assert res.json()["data"] == {"kind": "medication", "count": 1}
    assert "降血壓藥" in router.sent[0][2]
    assert logs.recorded[0][1] == "medication"


def test_dispatch_medication_invalid_slot_400():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    res = _client(accounts=accounts).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication", "slot": "midnight"},
        headers=_auth(),
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_slot"


def test_dispatch_appointment_today_and_tomorrow_only_this_elder():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    accounts.save_guardian(Guardian("g1", "小明"))
    accounts.save_elder_guardian(ElderGuardian("e1", "g1", Role.PRIMARY, 1))
    appts = FakeAppointmentStore()
    appts.save(Appointment("a1", "e1", NOW.date().isoformat(), "心臟科"))
    appts.save(Appointment("a2", "e2", NOW.date().isoformat(), "別人的"))
    router = _FakeRouter()
    res = _client(accounts=accounts, appt_store=appts, channel_router=router).post(
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
        json={"kind": "medication", "slot": "morning"},
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
    meds = FakeMedicationStore()
    meds.save(Medication("m1", "e1", "降血壓藥", (MedicationSlot.MORNING,)))
    router = _FakeRouter()
    logs = FakeReminderLogStore()
    res = _client(
        accounts=accounts, med_store=meds, channel_router=router, reminder_logs=logs
    ).post(
        "/api/v1/admin/elders/e1/reminders/dispatch",
        json={"kind": "medication", "slot": "morning"},
        headers=_auth(),
    )
    assert res.status_code == 200
    assert "降血壓藥" in router.sent[0][2]
    assert logs.recorded[0][1] == "medication"
