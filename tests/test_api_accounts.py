from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService
from kinsun.appointment.service import AppointmentService
from kinsun.medication.service import MedicationService
from kinsun.web.api import create_api_router
from kinsun.web.auth import AuthError
from tests.fakes import (
    FakeAccountRepository,
    FakeAppointmentStore,
    FakeMedicationStore,
    FakeReminderLogStore,
    FakeRiskEventStore,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, tzinfo=TPE)


class _FakeVerifier:
    def __init__(self, user_id="U-son", boom=False):
        self._user_id = user_id
        self._boom = boom

    def verify(self, id_token):
        if self._boom:
            raise AuthError("bad")
        return self._user_id


def _setup(user_id="U-son"):
    repo = FakeAccountRepository()
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )
    app = FastAPI()
    app.include_router(
        create_api_router(
            verifier=_FakeVerifier(user_id),
            accounts=accounts,
            medications=MedicationService(FakeMedicationStore()),
            appointments=AppointmentService(FakeAppointmentStore()),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
        )
    )
    return TestClient(app), accounts


def _auth():
    return {"Authorization": "Bearer tok"}


def test_create_elder_returns_binding_code():
    client, accounts = _setup()
    res = client.post(
        "/api/elders", headers=_auth(), json={"elder_name": "阿公", "guardian_name": "兒子"}
    )
    assert res.status_code == 201
    code = res.json()["invite_code"]
    assert [e.name for e in accounts.elders_managed_by("U-son")] == ["阿公"]
    assert accounts.preview_invite(code).role == InviteRole.ELDER


def test_create_elder_rejects_empty_name():
    client, _ = _setup()
    res = client.post(
        "/api/elders", headers=_auth(), json={"elder_name": "  ", "guardian_name": "兒子"}
    )
    assert res.status_code == 400


def test_create_elder_requires_token():
    client, _ = _setup()
    assert client.post("/api/elders", json={"elder_name": "阿公"}).status_code == 401


def test_guardian_invite_for_managed_elder():
    client, accounts = _setup()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    res = client.post(f"/api/elders/{elder.elder_id}/guardian-invites", headers=_auth())
    assert res.status_code == 201
    assert accounts.preview_invite(res.json()["invite_code"]).role == InviteRole.GUARDIAN


def test_guardian_invite_rejects_unmanaged_elder():
    client, accounts = _setup(user_id="U-stranger")
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    res = client.post(f"/api/elders/{elder.elder_id}/guardian-invites", headers=_auth())
    assert res.status_code == 404


def test_guardian_invite_requires_token():
    client, accounts = _setup()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    assert client.post(f"/api/elders/{elder.elder_id}/guardian-invites").status_code == 401
