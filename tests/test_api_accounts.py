from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from kinsun.web.auth import AuthError, LineIdentity
from kinsun.web.routers import create_guardian_face_router
from tests.fakes import (
    FakeAccountStore,
    FakeConversationSummaryStore,
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
        return LineIdentity(self._line_user_id, "兒子")


def _setup(line_user_id="U-son"):
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: next(codes)
    )
    app = FastAPI()
    app.include_router(
        create_guardian_face_router(
            verifier=_FakeVerifier(line_user_id),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: NOW),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
            summaries=FakeConversationSummaryStore(),
            appointment_hour=8,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), accounts


def _auth():
    return {"Authorization": "Bearer tok"}


def test_create_elder_returns_binding_code():
    """payload 三端統一 {name}（✅ 庚-29／F-9）：LIFF 首建家屬檔命名取
    ID token 的 LINE 顯示名稱（替身回「兒子」），不再由前端自送 guardian_name。"""
    client, accounts = _setup()
    res = client.post("/api/v1/elders", headers=_auth(), json={"name": "阿公"})
    assert res.status_code == 201
    code = res.json()["data"]["invite_code"]
    assert [e.name for e in accounts.elders_managed_by("U-son")] == ["阿公"]
    assert accounts.preview_invite(code).role == InviteRole.ELDER


def test_liff_first_elder_names_guardian_from_id_token():
    """✅ 庚-29：LIFF 首次建長輩時，家屬檔名字取自 ID token 顯示名稱（替身＝兒子）。"""
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    app = FastAPI()
    app.include_router(
        create_guardian_face_router(
            verifier=_FakeVerifier(),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: NOW),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
            summaries=FakeConversationSummaryStore(),
            appointment_hour=8,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app)
    res = client.post("/api/v1/elders", headers=_auth(), json={"name": "阿公"})
    assert res.status_code == 201
    assert [g.name for g in repo.guardians.values()] == ["兒子"]


def test_create_elder_rejects_empty_name():
    client, _ = _setup()
    res = client.post("/api/v1/elders", headers=_auth(), json={"name": "  "})
    assert res.status_code == 400


def test_create_elder_requires_token():
    client, _ = _setup()
    assert client.post("/api/v1/elders", json={"name": "阿公"}).status_code == 401


def test_guardian_invite_for_managed_elder():
    client, accounts = _setup()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    res = client.post(f"/api/v1/elders/{elder.elder_id}/guardian-invites", headers=_auth())
    assert res.status_code == 201
    assert accounts.preview_invite(res.json()["data"]["invite_code"]).role == InviteRole.GUARDIAN


def test_guardian_invite_rejects_unmanaged_elder():
    client, accounts = _setup(line_user_id="U-stranger")
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    res = client.post(f"/api/v1/elders/{elder.elder_id}/guardian-invites", headers=_auth())
    assert res.status_code == 404


def test_guardian_invite_requires_token():
    client, accounts = _setup()
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    assert client.post(f"/api/v1/elders/{elder.elder_id}/guardian-invites").status_code == 401
