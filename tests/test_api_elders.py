from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.medication.service import MedicationService
from kinsun.web.api import create_api_router
from kinsun.web.auth import AuthError
from tests.fakes import FakeAccountRepository, FakeMedicationStore

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


def _accounts():
    repo = FakeAccountRepository()
    ids = (f"id{i}" for i in count(1))
    svc = AccountService(repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c")
    svc.create_elder("U-son", "兒子", "阿公")
    return svc


def _client(verifier, accounts):
    app = FastAPI()
    app.include_router(
        create_api_router(
            verifier=verifier,
            accounts=accounts,
            medications=MedicationService(FakeMedicationStore()),
        )
    )
    return TestClient(app)


def test_lists_elders_for_authenticated_guardian():
    client = _client(_FakeVerifier("U-son"), _accounts())
    res = client.get("/api/me/elders", headers={"Authorization": "Bearer tok"})
    assert res.status_code == 200
    assert [e["name"] for e in res.json()["elders"]] == ["阿公"]


def test_missing_token_returns_401():
    client = _client(_FakeVerifier(), _accounts())
    assert client.get("/api/me/elders").status_code == 401


def test_non_bearer_returns_401():
    client = _client(_FakeVerifier(), _accounts())
    assert client.get("/api/me/elders", headers={"Authorization": "Basic x"}).status_code == 401


def test_invalid_token_returns_401():
    client = _client(_FakeVerifier(boom=True), _accounts())
    assert client.get("/api/me/elders", headers={"Authorization": "Bearer tok"}).status_code == 401


def test_guardian_without_elders_returns_empty():
    client = _client(_FakeVerifier("U-stranger"), _accounts())
    res = client.get("/api/me/elders", headers={"Authorization": "Bearer tok"})
    assert res.status_code == 200
    assert res.json() == {"elders": []}
