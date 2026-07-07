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


def _accounts():
    repo = FakeAccountStore()
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
            appointments=AppointmentService(FakeAppointmentStore()),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
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


def test_app_token_full_guardian_flow():
    """App token 認證：註冊 → 建長輩 → 列長輩 → 產家屬邀請碼，全程不經 LIFF。"""
    repo_svc = _accounts()
    _, token = repo_svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    client = _client(_FakeVerifier(boom=True), repo_svc)  # LIFF 驗證炸掉也不影響 App token 路徑
    auth = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/elders", json={"name": "阿嬤"}, headers=auth)
    assert created.status_code == 201
    elder_id = created.json()["elder_id"]
    assert created.json()["invite_code"]

    listed = client.get("/api/me/elders", headers=auth)
    assert listed.status_code == 200
    assert {e["elder_id"] for e in listed.json()["elders"]} == {elder_id}

    invite = client.post(f"/api/elders/{elder_id}/guardian-invites", headers=auth)
    assert invite.status_code == 201


def test_app_token_cannot_touch_others_elder():
    repo_svc = _accounts()  # 內含 U-son 的長輩（LIFF 家屬）
    _, token = repo_svc.register_guardian_account("other@example.com", "correct-horse-8", "路人")
    client = _client(_FakeVerifier(), repo_svc)
    other_elder = repo_svc.elders_managed_by("U-son")[0]
    res = client.post(
        f"/api/elders/{other_elder.elder_id}/guardian-invites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_elder_device_token_rejected_on_guardian_api():
    from kinsun.accounts.models import ConsentBy, InviteRole

    repo_svc = _accounts()
    elder = repo_svc.elders_managed_by("U-son")[0]
    inv = repo_svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    _, device_token = repo_svc.bind_elder_device(inv.code, consent_by=ConsentBy.PROXY)
    client = _client(_FakeVerifier(boom=True), repo_svc)
    res = client.get("/api/me/elders", headers={"Authorization": f"Bearer {device_token}"})
    assert res.status_code == 401
