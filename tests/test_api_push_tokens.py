"""裝置推播 token 註冊端點。

安全重點：主體一律由 Authorization 決定。若讓呼叫端自報身分，任何人都能把
別人的用藥提醒與危急警報導到自己的手機——那比收不到提醒更糟。
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import ConsentBy, InviteRole, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.notifications.push_tokens import FakePushTokenStore
from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers import create_app_auth_router
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 8, 0, tzinfo=TPE)


def _service():
    ids = (f"id{i}" for i in count(1))
    codes = (f"code{i}" for i in count(1))
    return AccountService(
        FakeAccountStore(),
        clock=lambda: NOW,
        new_id=lambda: next(ids),
        new_code=lambda: next(codes),
    )


def _client(svc, push_tokens=None):
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_auth_router(accounts=svc, push_tokens=push_tokens), prefix="/api/v1"
    )
    return TestClient(app)


def _family(svc, *, elder_name="王阿嬤", email="g@example.com"):
    guardian, guardian_token = svc.register_guardian_account(email, "correct-horse-8", "兒子")
    elder = svc.create_elder_for_guardian(guardian.guardian_id, elder_name)
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    _, elder_token = svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    return guardian.guardian_id, guardian_token, elder.elder_id, elder_token


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_elder_registers_device():
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    store = FakePushTokenStore()

    res = _client(svc, store).post(
        "/api/v1/push-tokens",
        json={"token": "ExponentPushToken[abc]", "platform": "android"},
        headers=_bearer(elder_token),
    )

    assert res.status_code == 201
    assert res.json()["data"]["registered"] is True
    rows = store.list_for_principal(PrincipalType.ELDER, elder_id)
    assert [r.token for r in rows] == ["ExponentPushToken[abc]"]
    assert rows[0].platform == "android"


def test_guardian_registers_device():
    """家屬也要收推播（危急警報），共用同一支端點。"""
    svc = _service()
    guardian_id, guardian_token, _, _ = _family(svc)
    store = FakePushTokenStore()

    res = _client(svc, store).post(
        "/api/v1/push-tokens",
        json={"token": "ExponentPushToken[xyz]", "platform": "ios"},
        headers=_bearer(guardian_token),
    )

    assert res.status_code == 201
    assert [r.token for r in store.list_for_principal(PrincipalType.GUARDIAN, guardian_id)] == [
        "ExponentPushToken[xyz]"
    ]


def test_token_binds_to_authenticated_principal_not_request_body():
    """呼叫端就算在 body 裡塞別人的 id 也沒用——主體只看 Authorization。"""
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    store = FakePushTokenStore()

    _client(svc, store).post(
        "/api/v1/push-tokens",
        json={
            "token": "ExponentPushToken[abc]",
            "platform": "android",
            "principal_id": "別人的id",
            "principal_type": "guardian",
        },
        headers=_bearer(elder_token),
    )

    assert store.list_for_principal(PrincipalType.GUARDIAN, "別人的id") == []
    assert len(store.list_for_principal(PrincipalType.ELDER, elder_id)) == 1


def test_re_register_same_token_rebinds():
    """同一台裝置換人用：改綁，不留兩列。"""
    svc = _service()
    guardian_id, guardian_token, elder_id, elder_token = _family(svc)
    store = FakePushTokenStore()
    client = _client(svc, store)
    payload = {"token": "ExponentPushToken[same]", "platform": "android"}

    client.post("/api/v1/push-tokens", json=payload, headers=_bearer(elder_token))
    client.post("/api/v1/push-tokens", json=payload, headers=_bearer(guardian_token))

    assert store.list_for_principal(PrincipalType.ELDER, elder_id) == []
    assert len(store.list_for_principal(PrincipalType.GUARDIAN, guardian_id)) == 1


def test_unknown_platform_rejected():
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, FakePushTokenStore()).post(
        "/api/v1/push-tokens",
        json={"token": "tok", "platform": "windows-phone"},
        headers=_bearer(elder_token),
    )

    assert res.status_code == 400


def test_platform_is_case_insensitive():
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    store = FakePushTokenStore()

    res = _client(svc, store).post(
        "/api/v1/push-tokens",
        json={"token": "tok", "platform": "Android"},
        headers=_bearer(elder_token),
    )

    assert res.status_code == 201
    assert store.list_for_principal(PrincipalType.ELDER, elder_id)[0].platform == "android"


def test_empty_token_rejected():
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, FakePushTokenStore()).post(
        "/api/v1/push-tokens",
        json={"token": "", "platform": "android"},
        headers=_bearer(elder_token),
    )

    assert res.status_code == 422


def test_missing_token_rejected():
    svc = _service()
    res = _client(svc, FakePushTokenStore()).post(
        "/api/v1/push-tokens", json={"token": "tok", "platform": "android"}
    )
    assert res.status_code == 401


def test_without_store_still_returns_201():
    """未配置推播的部署：收下但不存，App 不必分辨伺服器版本。"""
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, None).post(
        "/api/v1/push-tokens",
        json={"token": "tok", "platform": "android"},
        headers=_bearer(elder_token),
    )

    assert res.status_code == 201
    assert res.json()["data"]["registered"] is False


# ── 移除 ──────────────────────────────────────────────────────


def test_owner_can_remove_own_token():
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    store = FakePushTokenStore()
    store.save("tok", PrincipalType.ELDER, elder_id, "android")

    res = _client(svc, store).delete("/api/v1/push-tokens/tok", headers=_bearer(elder_token))

    assert res.status_code == 204
    assert store.list_for_principal(PrincipalType.ELDER, elder_id) == []


def test_cannot_remove_someone_elses_token():
    """否則知道別人 token 的人可以讓對方從此收不到提醒。"""
    svc = _service()
    _, _, _, elder_token = _family(svc)
    store = FakePushTokenStore()
    store.save("victim-token", PrincipalType.ELDER, "另一位長輩", "android")

    res = _client(svc, store).delete(
        "/api/v1/push-tokens/victim-token", headers=_bearer(elder_token)
    )

    assert res.status_code == 204
    assert len(store.list_for_principal(PrincipalType.ELDER, "另一位長輩")) == 1


def test_remove_without_token_rejected():
    svc = _service()
    res = _client(svc, FakePushTokenStore()).delete("/api/v1/push-tokens/tok")
    assert res.status_code == 401
