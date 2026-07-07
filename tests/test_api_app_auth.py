"""App 認證三端點測試：註冊／登入／長輩裝置綁定。"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService
from kinsun.web.app_api import create_app_api_router
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=TPE)


def _service():
    ids = (f"id{i}" for i in count(1))
    return AccountService(
        FakeAccountStore(), clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "code1"
    )


def _client(svc=None):
    app = FastAPI()
    app.include_router(create_app_api_router(accounts=svc or _service()))
    return TestClient(app)


def test_register_returns_token_201():
    client = _client()
    res = client.post(
        "/api/app/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "兒子"
    assert body["guardian_id"]
    assert len(body["token"]) >= 32


def test_register_duplicate_email_409():
    svc = _service()
    client = _client(svc)
    payload = {"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"}
    assert client.post("/api/app/guardians", json=payload).status_code == 201
    res = client.post("/api/app/guardians", json=payload)
    assert res.status_code == 409
    assert res.json()["detail"] == "email_taken"


def test_register_short_password_422():
    res = _client().post(
        "/api/app/guardians",
        json={"email": "son@example.com", "password": "short", "name": "兒子"},
    )
    assert res.status_code == 422


def test_login_success_and_failure():
    svc = _service()
    client = _client(svc)
    client.post(
        "/api/app/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    ok = client.post(
        "/api/app/sessions", json={"email": "Son@Example.com", "password": "correct-horse-8"}
    )
    assert ok.status_code == 200
    assert len(ok.json()["token"]) >= 32
    bad = client.post(
        "/api/app/sessions", json={"email": "son@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid_credentials"


def test_device_binding_success_and_errors():
    svc = _service()
    client = _client(svc)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    ok = client.post("/api/app/device-bindings", json={"code": invite.code})
    assert ok.status_code == 201
    body = ok.json()
    assert body["elder_id"] == elder.elder_id
    assert body["name"] == "阿公"
    assert len(body["token"]) >= 32
    # 一次性：再用同碼 409 used。
    again = client.post("/api/app/device-bindings", json={"code": invite.code})
    assert again.status_code == 409
    assert again.json()["detail"] == "used"
    # 查無此碼 404。
    assert client.post("/api/app/device-bindings", json={"code": "nope"}).status_code == 404
