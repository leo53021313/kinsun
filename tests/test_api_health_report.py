from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.appointment.service import AppointmentService
from kinsun.medication.service import MedicationService
from kinsun.reports.reminders import ReminderLog
from kinsun.safety.events import RiskEvent
from kinsun.safety.tiers import RiskTier
from kinsun.web.api import create_api_router
from tests.fakes import FakeAccountRepository, FakeAppointmentStore, FakeMedicationStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=TPE)
RECENT = (NOW - timedelta(days=5)).timestamp()
OLD = (NOW - timedelta(days=40)).timestamp()


class _FakeVerifier:
    def __init__(self, user_id="U-son"):
        self._user_id = user_id

    def verify(self, id_token):
        return self._user_id


class _RiskEvents:
    def __init__(self, events):
        self._events = events

    def list_for_session(self, session_id):
        return self._events


class _Reminders:
    def __init__(self, logs):
        self._logs = logs

    def list_for_elder(self, elder_id):
        return self._logs


def _client(user_id, *, risks, reminders, bind_elder=True):
    repo = FakeAccountRepository()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    if bind_elder:
        from kinsun.accounts.models import Elder

        repo.save_elder(Elder(elder.elder_id, "阿公", "U-elder"))
    app = FastAPI()
    app.include_router(
        create_api_router(
            verifier=_FakeVerifier(user_id),
            accounts=accounts,
            medications=MedicationService(FakeMedicationStore()),
            appointments=AppointmentService(FakeAppointmentStore()),
            clock=lambda: NOW,
            risk_events=_RiskEvents(risks),
            reminder_logs=_Reminders(reminders),
        )
    )
    return TestClient(app), elder.elder_id


def _auth():
    return {"Authorization": "Bearer tok"}


def test_health_report_recent_only():
    risks = [
        RiskEvent("r1", "U-elder", RiskTier.L3, "昏倒", RECENT),
        RiskEvent("r0", "U-elder", RiskTier.L2, "舊事件", OLD),
    ]
    reminders = [
        ReminderLog("m1", "e", "medication", "早上用藥：A", RECENT),
        ReminderLog("m0", "e", "appointment", "舊提醒", OLD),
    ]
    client, elder_id = _client("U-son", risks=risks, reminders=reminders)
    res = client.get(f"/api/elders/{elder_id}/health-report", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert [e["reason"] for e in body["risk_events"]] == ["昏倒"]
    assert body["risk_events"][0]["tier"] == 3
    assert [r["content"] for r in body["reminders"]] == ["早上用藥：A"]


def test_health_report_rejects_unmanaged():
    client, elder_id = _client("U-stranger", risks=[], reminders=[])
    assert client.get(f"/api/elders/{elder_id}/health-report", headers=_auth()).status_code == 404


def test_health_report_requires_token():
    client, elder_id = _client("U-son", risks=[], reminders=[])
    assert client.get(f"/api/elders/{elder_id}/health-report").status_code == 401


def test_health_report_unbound_elder_has_no_risks():
    reminders = [ReminderLog("m1", "e", "medication", "早上用藥：A", RECENT)]
    client, elder_id = _client("U-son", risks=[], reminders=reminders, bind_elder=False)
    res = client.get(f"/api/elders/{elder_id}/health-report", headers=_auth())
    assert res.status_code == 200
    assert res.json()["risk_events"] == []
    assert [r["content"] for r in res.json()["reminders"]] == ["早上用藥：A"]
