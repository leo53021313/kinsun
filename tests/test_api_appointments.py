from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.appointment.service import AppointmentService
from kinsun.medication.service import MedicationService
from kinsun.web.api import create_api_router
from kinsun.web.auth import AuthError
from tests.fakes import FakeAccountRepository, FakeAppointmentStore, FakeMedicationStore

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
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    appt_ids = (f"a{i}" for i in count(1))
    appointments = AppointmentService(FakeAppointmentStore(), new_id=lambda: next(appt_ids))
    app = FastAPI()
    app.include_router(
        create_api_router(
            verifier=_FakeVerifier(user_id),
            accounts=accounts,
            medications=MedicationService(FakeMedicationStore()),
            appointments=appointments,
            clock=lambda: NOW,
        )
    )
    return TestClient(app), elder.elder_id


def _auth():
    return {"Authorization": "Bearer tok"}


def _add(client, elder_id, date="2026-08-01", label="回診"):
    res = client.post(
        f"/api/elders/{elder_id}/appointments",
        headers=_auth(),
        json={"date": date, "label": label},
    )
    return res.json()["appt_id"]


def test_list_requires_management():
    client, elder_id = _setup(user_id="U-stranger")
    assert client.get(f"/api/elders/{elder_id}/appointments", headers=_auth()).status_code == 404


def test_add_then_list():
    client, elder_id = _setup()
    res = client.post(
        f"/api/elders/{elder_id}/appointments",
        headers=_auth(),
        json={"date": "2026-08-01", "label": "心臟科回診"},
    )
    assert res.status_code == 201
    assert res.json()["date"] == "2026-08-01"
    listed = client.get(f"/api/elders/{elder_id}/appointments", headers=_auth()).json()
    assert [a["label"] for a in listed["appointments"]] == ["心臟科回診"]


def test_add_rejects_past_date():
    client, elder_id = _setup()
    res = client.post(
        f"/api/elders/{elder_id}/appointments",
        headers=_auth(),
        json={"date": "2026-07-01", "label": "回診"},
    )
    assert res.status_code == 400


def test_add_rejects_bad_date_and_empty_label():
    client, elder_id = _setup()
    bad_date = client.post(
        f"/api/elders/{elder_id}/appointments",
        headers=_auth(),
        json={"date": "abc", "label": "回診"},
    )
    empty_label = client.post(
        f"/api/elders/{elder_id}/appointments",
        headers=_auth(),
        json={"date": "2026-08-01", "label": "  "},
    )
    assert bad_date.status_code == 400
    assert empty_label.status_code == 400


def test_update_changes_appt():
    client, elder_id = _setup()
    appt_id = _add(client, elder_id, "2026-08-01", "舊")
    res = client.put(
        f"/api/elders/{elder_id}/appointments/{appt_id}",
        headers=_auth(),
        json={"date": "2026-08-05", "label": "新"},
    )
    assert res.status_code == 200
    listed = client.get(f"/api/elders/{elder_id}/appointments", headers=_auth()).json()
    assert listed["appointments"][0]["date"] == "2026-08-05"
    assert listed["appointments"][0]["label"] == "新"


def test_update_rejects_appt_not_under_elder():
    client, elder_id = _setup()
    res = client.put(
        f"/api/elders/{elder_id}/appointments/ghost",
        headers=_auth(),
        json={"date": "2026-08-01", "label": "x"},
    )
    assert res.status_code == 404


def test_delete_removes():
    client, elder_id = _setup()
    appt_id = _add(client, elder_id)
    assert (
        client.delete(
            f"/api/elders/{elder_id}/appointments/{appt_id}", headers=_auth()
        ).status_code
        == 204
    )
    listed = client.get(f"/api/elders/{elder_id}/appointments", headers=_auth()).json()
    assert listed["appointments"] == []


def test_delete_rejects_appt_not_under_elder():
    client, elder_id = _setup()
    assert (
        client.delete(
            f"/api/elders/{elder_id}/appointments/ghost", headers=_auth()
        ).status_code
        == 404
    )


def test_requires_token():
    client, elder_id = _setup()
    assert client.get(f"/api/elders/{elder_id}/appointments").status_code == 401
