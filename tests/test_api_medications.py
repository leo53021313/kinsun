from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.appointments.service import AppointmentService
from kinsun.medications.service import MedicationService
from kinsun.web.api import create_api_router
from kinsun.web.auth import AuthError
from tests.fakes import (
    FakeAccountStore,
    FakeAppointmentStore,
    FakeMedicationStore,
    FakeReminderLogStore,
    FakeRiskEventStore,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, tzinfo=TPE)


class _FakeVerifier:
    def __init__(self, line_user_id="U-son", boom=False):
        self._line_user_id = line_user_id
        self._boom = boom

    def verify(self, id_token):
        if self._boom:
            raise AuthError("bad")
        return self._line_user_id


def _setup(line_user_id="U-son"):
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    med_ids = (f"m{i}" for i in count(1))
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: next(med_ids))
    app = FastAPI()
    app.include_router(
        create_api_router(
            verifier=_FakeVerifier(line_user_id),
            accounts=accounts,
            medications=medications,
            appointments=AppointmentService(FakeAppointmentStore()),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
        )
    )
    return TestClient(app), elder.elder_id


def _auth():
    return {"Authorization": "Bearer tok"}


def _add(client, elder_id, name="藥", slots=("morning",)):
    res = client.post(
        f"/api/elders/{elder_id}/medications",
        headers=_auth(),
        json={"name": name, "slots": list(slots)},
    )
    return res.json()["med_id"]


def test_list_requires_management():
    client, elder_id = _setup(line_user_id="U-stranger")
    assert client.get(f"/api/elders/{elder_id}/medications", headers=_auth()).status_code == 404


def test_add_then_list():
    client, elder_id = _setup()
    res = client.post(
        f"/api/elders/{elder_id}/medications",
        headers=_auth(),
        json={"name": "降血壓藥", "slots": ["morning", "evening"]},
    )
    assert res.status_code == 201
    assert res.json()["slots"] == ["morning", "evening"]
    listed = client.get(f"/api/elders/{elder_id}/medications", headers=_auth()).json()
    assert [m["name"] for m in listed["medications"]] == ["降血壓藥"]


def test_add_rejects_empty_name():
    client, elder_id = _setup()
    res = client.post(
        f"/api/elders/{elder_id}/medications",
        headers=_auth(),
        json={"name": "  ", "slots": ["morning"]},
    )
    assert res.status_code == 400


def test_add_rejects_bad_slots():
    client, elder_id = _setup()
    empty = client.post(
        f"/api/elders/{elder_id}/medications", headers=_auth(), json={"name": "藥", "slots": []}
    )
    bogus = client.post(
        f"/api/elders/{elder_id}/medications",
        headers=_auth(),
        json={"name": "藥", "slots": ["bogus"]},
    )
    assert empty.status_code == 400
    assert bogus.status_code == 400


def test_update_changes_med():
    client, elder_id = _setup()
    med_id = _add(client, elder_id, "舊", ["morning"])
    res = client.put(
        f"/api/elders/{elder_id}/medications/{med_id}",
        headers=_auth(),
        json={"name": "新", "slots": ["evening"]},
    )
    assert res.status_code == 200
    listed = client.get(f"/api/elders/{elder_id}/medications", headers=_auth()).json()
    assert listed["medications"][0]["name"] == "新"
    assert listed["medications"][0]["slots"] == ["evening"]


def test_update_rejects_med_not_under_elder():
    client, elder_id = _setup()
    res = client.put(
        f"/api/elders/{elder_id}/medications/ghost",
        headers=_auth(),
        json={"name": "x", "slots": ["morning"]},
    )
    assert res.status_code == 404


def test_delete_removes():
    client, elder_id = _setup()
    med_id = _add(client, elder_id)
    assert (
        client.delete(f"/api/elders/{elder_id}/medications/{med_id}", headers=_auth()).status_code
        == 204
    )
    listed = client.get(f"/api/elders/{elder_id}/medications", headers=_auth()).json()
    assert listed["medications"] == []


def test_delete_rejects_med_not_under_elder():
    client, elder_id = _setup()
    assert (
        client.delete(f"/api/elders/{elder_id}/medications/ghost", headers=_auth()).status_code
        == 404
    )


def test_requires_token():
    client, elder_id = _setup()
    assert client.get(f"/api/elders/{elder_id}/medications").status_code == 401
