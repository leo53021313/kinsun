from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _accounts():
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    svc = AccountService(repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c")
    svc.create_elder("U-son", "兒子", "阿公")
    return svc


def _client(verifier, accounts):
    app = FastAPI()
    app.include_router(
        create_guardian_face_router(
            verifier=verifier,
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
    return TestClient(app)


def test_lists_elders_for_authenticated_guardian():
    client = _client(_FakeVerifier("U-son"), _accounts())
    res = client.get("/api/v1/elders", headers={"Authorization": "Bearer tok"})
    assert res.status_code == 200
    assert [e["name"] for e in res.json()["data"]] == ["阿公"]


def test_missing_token_returns_401():
    client = _client(_FakeVerifier(), _accounts())
    assert client.get("/api/v1/elders").status_code == 401


def test_non_bearer_returns_401():
    client = _client(_FakeVerifier(), _accounts())
    assert client.get("/api/v1/elders", headers={"Authorization": "Basic x"}).status_code == 401


def test_invalid_token_returns_401():
    client = _client(_FakeVerifier(boom=True), _accounts())
    assert client.get("/api/v1/elders", headers={"Authorization": "Bearer tok"}).status_code == 401


def test_guardian_without_elders_returns_empty():
    client = _client(_FakeVerifier("U-stranger"), _accounts())
    res = client.get("/api/v1/elders", headers={"Authorization": "Bearer tok"})
    assert res.status_code == 200
    assert res.json()["data"] == []


def test_app_token_full_guardian_flow():
    """App token 認證：註冊 → 建長輩 → 列長輩 → 產家屬邀請碼，全程不經 LIFF。"""
    repo_svc = _accounts()
    _, token = repo_svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    client = _client(_FakeVerifier(boom=True), repo_svc)  # LIFF 驗證炸掉也不影響 App token 路徑
    auth = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/elders", json={"name": "阿嬤"}, headers=auth)
    assert created.status_code == 201
    elder_id = created.json()["data"]["elder_id"]
    assert created.json()["data"]["invite_code"]

    listed = client.get("/api/v1/elders", headers=auth)
    assert listed.status_code == 200
    assert {e["elder_id"] for e in listed.json()["data"]} == {elder_id}

    invite = client.post(f"/api/v1/elders/{elder_id}/guardian-invites", headers=auth)
    assert invite.status_code == 201


def test_revoke_device_binding_invalidates_and_reissues():
    """✅ D-25 修訂（乙-3）：家屬作廢長輩裝置——舊裝置 token 失效＋回新綁定碼可重綁。"""
    from kinsun.accounts.models import ConsentBy

    repo_svc = _accounts()
    _, token = repo_svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    client = _client(_FakeVerifier(boom=True), repo_svc)
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/elders", json={"name": "阿嬤"}, headers=auth)
    elder_id = created.json()["data"]["elder_id"]
    _, elder_token = repo_svc.bind_elder_device(
        created.json()["data"]["invite_code"], consent_by=ConsentBy.PROXY
    )
    assert repo_svc.authenticate_token(elder_token) is not None
    assert repo_svc.app_external_id_of_elder(elder_id) is not None

    res = client.delete(f"/api/v1/elders/{elder_id}/device-bindings", headers=auth)
    assert res.status_code == 200
    new_code = res.json()["data"]["invite_code"]
    # 舊裝置 token 與 App 綁定全數作廢；新碼可重新綁回同一位長輩。
    assert repo_svc.authenticate_token(elder_token) is None
    assert repo_svc.app_external_id_of_elder(elder_id) is None
    elder, _ = repo_svc.bind_elder_device(new_code, consent_by=ConsentBy.PROXY)
    assert elder.elder_id == elder_id


def test_revoke_device_binding_rejects_unmanaged():
    repo_svc = _accounts()
    _, token = repo_svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    client = _client(_FakeVerifier(boom=True), repo_svc)
    res = client.delete(
        "/api/v1/elders/ghost/device-bindings", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 404


def test_app_token_cannot_touch_others_elder():
    repo_svc = _accounts()  # 內含 U-son 的長輩（LIFF 家屬）
    _, token = repo_svc.register_guardian_account("other@example.com", "correct-horse-8", "路人")
    client = _client(_FakeVerifier(), repo_svc)
    other_elder = repo_svc.elders_managed_by("U-son")[0]
    res = client.post(
        f"/api/v1/elders/{other_elder.elder_id}/guardian-invites",
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
    res = client.get("/api/v1/elders", headers={"Authorization": f"Bearer {device_token}"})
    assert res.status_code == 401


# --- 家屬代辦長輩帳密（✅ D-71 己-6）：PUT /elders/{elder_id}/account ---


def _put_account(client, elder_id, payload):
    return client.put(
        f"/api/v1/elders/{elder_id}/account",
        json=payload,
        headers={"Authorization": "Bearer tok"},
    )


def test_set_elder_account_ok_and_resettable():
    accounts = _accounts()
    elder_id = accounts.elders_managed_by("U-son")[0].elder_id
    client = _client(_FakeVerifier("U-son"), accounts)
    res = _put_account(client, elder_id, {"phone": "0912-345-678", "password": "sunsun-8888"})
    assert res.status_code == 200
    assert res.json()["data"]["elder_id"] == elder_id
    # PUT＝upsert：同長輩重呼即重設密碼，不衝突。
    res2 = _put_account(client, elder_id, {"phone": "0912345678", "password": "new-pass-888"})
    assert res2.status_code == 200


def test_set_elder_account_invalid_phone_400():
    accounts = _accounts()
    elder_id = accounts.elders_managed_by("U-son")[0].elder_id
    client = _client(_FakeVerifier("U-son"), accounts)
    res = _put_account(client, elder_id, {"phone": "abcd-efgh", "password": "sunsun-8888"})
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_phone"


def test_set_elder_account_phone_taken_409():
    accounts = _accounts()
    elder_id = accounts.elders_managed_by("U-son")[0].elder_id
    other = accounts.create_elder("U-son", "兒子", "阿嬤")
    client = _client(_FakeVerifier("U-son"), accounts)
    assert (
        _put_account(
            client, elder_id, {"phone": "0912345678", "password": "sunsun-8888"}
        ).status_code
        == 200
    )
    res = _put_account(client, other.elder_id, {"phone": "0912345678", "password": "other-888"})
    assert res.status_code == 409
    assert res.json()["detail"] == "phone_taken"


def test_set_elder_account_scope_guard_404():
    accounts = _accounts()
    elder_id = accounts.elders_managed_by("U-son")[0].elder_id
    stranger = _client(_FakeVerifier("U-stranger"), accounts)
    res = _put_account(stranger, elder_id, {"phone": "0912345678", "password": "sunsun-8888"})
    assert res.status_code == 404


# --- 稱謂欄位（2026-07-17：金孫亂猜「阿公／阿嬤」的資料源修正）---


def _app_client_with_token():
    repo_svc = _accounts()
    _, token = repo_svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    client = _client(_FakeVerifier(boom=True), repo_svc)
    return client, {"Authorization": f"Bearer {token}"}


def test_create_elder_with_nickname():
    client, auth = _app_client_with_token()
    created = client.post(
        "/api/v1/elders", json={"name": "王秀英", "nickname": "秀英阿嬤"}, headers=auth
    )
    assert created.status_code == 201
    assert created.json()["data"]["nickname"] == "秀英阿嬤"

    listed = client.get("/api/v1/elders", headers=auth)
    rows = {e["name"]: e for e in listed.json()["data"]}
    assert rows["王秀英"]["nickname"] == "秀英阿嬤"


def test_create_elder_without_nickname_defaults_empty():
    client, auth = _app_client_with_token()
    created = client.post("/api/v1/elders", json={"name": "陳阿土"}, headers=auth)
    assert created.status_code == 201
    assert created.json()["data"]["nickname"] == ""


def test_update_elder_profile_sets_nickname():
    client, auth = _app_client_with_token()
    elder_id = client.post("/api/v1/elders", json={"name": "王秀英"}, headers=auth).json()["data"][
        "elder_id"
    ]
    res = client.put(
        f"/api/v1/elders/{elder_id}/profile", json={"nickname": "秀英阿嬤"}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["data"]["nickname"] == "秀英阿嬤"

    listed = client.get("/api/v1/elders", headers=auth)
    assert [e["nickname"] for e in listed.json()["data"] if e["elder_id"] == elder_id] == [
        "秀英阿嬤"
    ]


def test_update_elder_profile_rejects_unmanaged():
    client, auth = _app_client_with_token()
    res = client.put(
        "/api/v1/elders/id1/profile", json={"nickname": "亂改"}, headers=auth
    )  # id1 屬於 U-son（LIFF 家屬），不是本 App 家屬管的
    assert res.status_code == 404


def test_update_elder_profile_rejects_overlong_nickname():
    client, auth = _app_client_with_token()
    elder_id = client.post("/api/v1/elders", json={"name": "王秀英"}, headers=auth).json()["data"][
        "elder_id"
    ]
    res = client.put(
        f"/api/v1/elders/{elder_id}/profile", json={"nickname": "好" * 51}, headers=auth
    )
    assert res.status_code == 422
