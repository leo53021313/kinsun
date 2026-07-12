"""App 認證三端點測試：註冊／登入／長輩裝置綁定（含 per-IP 節流，✅ D-58）。"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import Channel, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.notifications.store import FakeAppNotificationStore
from kinsun.web.envelope import install_error_envelope
from kinsun.web.ratelimit import SlidingWindowRateLimiter
from kinsun.web.routers import create_app_auth_router
from tests.fakes import FakeAccountStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=TPE)


def _service():
    ids = (f"id{i}" for i in count(1))
    return AccountService(
        FakeAccountStore(), clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "code1"
    )


def _client(svc=None, rate_limiter=None, notifications=None):
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_auth_router(
            accounts=svc or _service(), rate_limiter=rate_limiter, notifications=notifications
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def test_register_returns_token_201():
    client = _client()
    res = client.post(
        "/api/v1/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    assert res.status_code == 201
    body = res.json()["data"]
    assert body["name"] == "兒子"
    assert body["guardian_id"]
    assert len(body["token"]) >= 32


def test_register_duplicate_email_409():
    svc = _service()
    client = _client(svc)
    payload = {"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"}
    assert client.post("/api/v1/guardians", json=payload).status_code == 201
    res = client.post("/api/v1/guardians", json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "email_taken"


def test_register_short_password_422_validation_envelope():
    """✅ D-24（乙-2）：pydantic 驗證錯誤統一改寫為信封＋meta.fields 明細。"""
    res = _client().post(
        "/api/v1/guardians",
        json={"email": "son@example.com", "password": "short", "name": "兒子"},
    )
    assert res.status_code == 422
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"]
    assert body["meta"]["fields"][0]["field"].endswith("password")


def test_error_message_is_human_readable():
    """✅ D-24（乙-2）：error.message 為繁中人話，UI 可直接顯示。"""
    res = _client().post(
        "/api/v1/sessions", json={"email": "no@example.com", "password": "wrong-password"}
    )
    assert res.json()["error"]["message"] == "帳號或密碼不正確"


def test_login_success_and_failure():
    svc = _service()
    client = _client(svc)
    client.post(
        "/api/v1/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    ok = client.post(
        "/api/v1/sessions", json={"email": "Son@Example.com", "password": "correct-horse-8"}
    )
    assert ok.status_code == 200
    assert len(ok.json()["data"]["token"]) >= 32
    bad = client.post(
        "/api/v1/sessions", json={"email": "son@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"


def test_device_binding_success_and_errors():
    svc = _service()
    client = _client(svc)
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    ok = client.post("/api/v1/device-bindings", json={"code": invite.code})
    assert ok.status_code == 201
    body = ok.json()["data"]
    assert body["elder_id"] == elder.elder_id
    assert body["name"] == "阿公"
    assert len(body["token"]) >= 32
    # 一次性：再用同碼 409 used。
    again = client.post("/api/v1/device-bindings", json={"code": invite.code})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invite_used"
    # 查無此碼 404。
    assert client.post("/api/v1/device-bindings", json={"code": "nope"}).status_code == 404


def test_register_creates_app_channel_binding():
    """✅ D-12（甲-6）：App 註冊的家屬要有 App 通道綁定，出站路由才觸達得到。"""
    svc = _service()
    guardian, _token = svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    assert svc.app_external_ids_of_guardian(guardian.guardian_id)


def test_login_backfills_missing_app_binding():
    """存量帳號（D-12 前註冊、無 App 綁定）登入時自動回填綁定。"""
    svc = _service()
    guardian, _ = svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    # 模擬存量狀態：移除 App 綁定。
    store = svc._repo  # noqa: SLF001 - 測試需操作替身內部狀態
    for key in [k for k, b in store.channel_bindings.items() if b.channel is Channel.APP]:
        del store.channel_bindings[key]
    assert svc.app_external_ids_of_guardian(guardian.guardian_id) == []
    svc.login_guardian("son@example.com", "correct-horse-8")
    assert svc.app_external_ids_of_guardian(guardian.guardian_id)


def _guardian_with_token(svc):
    client = _client(svc)
    res = client.post(
        "/api/v1/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    return res.json()["data"]["guardian_id"], res.json()["data"]["token"]


def test_notifications_requires_token():
    res = _client(notifications=FakeAppNotificationStore()).get("/api/v1/notifications")
    assert res.status_code == 401


def test_notifications_lists_guardian_items_recent_first():
    """✅ D-12（甲-6）：出站訊息落通知後，家屬憑 token 拉取自己的列表。"""
    svc = _service()
    notifications = FakeAppNotificationStore()
    client = _client(svc, notifications=notifications)
    res = client.post(
        "/api/v1/guardians",
        json={"email": "son@example.com", "password": "correct-horse-8", "name": "兒子"},
    )
    guardian_id, token = res.json()["data"]["guardian_id"], res.json()["data"]["token"]
    ext = svc.app_external_ids_of_guardian(guardian_id)[0]
    notifications.record(ext, "第一則")
    notifications.record(ext, "阿蘭提到跌倒，請留意")
    notifications.record("別人的外部識別", "不該看到")
    res = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()["data"]
    assert [i["content"] for i in items] == ["阿蘭提到跌倒，請留意", "第一則"]
    assert all("created_at" in i for i in items)


def test_logout_revokes_token():
    """✅ D-25 修訂（乙-3）：DELETE /sessions 撤銷當前 token（永久記住＋可主動登出）。"""
    svc = _service()
    client = _client(svc, notifications=FakeAppNotificationStore())
    _, token = _guardian_with_token(svc)
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/notifications", headers=auth).status_code == 200
    assert client.delete("/api/v1/sessions", headers=auth).status_code == 204
    assert client.get("/api/v1/notifications", headers=auth).status_code == 401


def test_logout_requires_valid_token():
    assert _client().delete("/api/v1/sessions").status_code == 401
    res = _client().delete("/api/v1/sessions", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401


def test_logout_all_revokes_every_device_token():
    """庚-05（A-47）：DELETE /sessions/all 撤銷該家屬全部 token，非只當前一顆。"""
    svc = _service()
    client = _client(svc, notifications=FakeAppNotificationStore())
    guardian_id, token_a = _guardian_with_token(svc)
    # 第二次登入拿到另一顆 token（模擬第二台裝置）。
    token_b = client.post(
        "/api/v1/sessions",
        json={"email": "son@example.com", "password": "correct-horse-8"},
    ).json()["data"]["token"]
    res = client.delete("/api/v1/sessions/all", headers={"Authorization": f"Bearer {token_a}"})
    assert res.status_code == 204
    # 兩顆 token 都失效。
    for token in (token_a, token_b):
        probe = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
        assert probe.status_code == 401


def test_logout_all_requires_guardian_token():
    assert _client().delete("/api/v1/sessions/all").status_code == 401
    res = _client().delete("/api/v1/sessions/all", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401


def test_login_unknown_email_still_runs_password_verify(monkeypatch):
    """✅ D-60（丙-11）：查無帳號也跑一次假雜湊驗證，補平計時信號。"""
    import kinsun.accounts.service as service_module

    calls = []
    monkeypatch.setattr(
        service_module, "verify_password", lambda pw, stored: calls.append(stored) or False
    )
    svc = _service()
    client = _client(svc)
    res = client.post(
        "/api/v1/sessions", json={"email": "no@example.com", "password": "whatever-8"}
    )
    assert res.status_code == 401
    assert len(calls) == 1  # 不存在的帳號也有一次驗證運算


def test_register_rejects_malformed_email():
    """✅ D-61（丙-11）：email 基本格式驗證（422 validation_error）。"""
    res = _client().post(
        "/api/v1/guardians",
        json={"email": "not-an-email", "password": "correct-horse-8", "name": "兒子"},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def _throttled_client(max_attempts=2):
    return _client(rate_limiter=SlidingWindowRateLimiter(max_attempts, 300.0))


def test_login_throttled_per_ip_429():
    client = _throttled_client(max_attempts=2)
    payload = {"email": "son@example.com", "password": "wrong-password"}
    assert client.post("/api/v1/sessions", json=payload).status_code == 401
    assert client.post("/api/v1/sessions", json=payload).status_code == 401
    res = client.post("/api/v1/sessions", json=payload)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "too_many_requests"


def test_throttle_isolated_by_forwarded_ip():
    """經 ngrok 轉發時以 X-Forwarded-For 第一段辨識來源：不同 IP 不互相影響。"""
    client = _throttled_client(max_attempts=1)
    payload = {"email": "son@example.com", "password": "wrong-password"}
    a = {"X-Forwarded-For": "1.2.3.4"}
    b = {"X-Forwarded-For": "5.6.7.8, 10.0.0.1"}
    assert client.post("/api/v1/sessions", json=payload, headers=a).status_code == 401
    assert client.post("/api/v1/sessions", json=payload, headers=a).status_code == 429
    assert client.post("/api/v1/sessions", json=payload, headers=b).status_code == 401


def test_register_and_binding_throttled_separately():
    """三端點各自計數：登入被擋不影響註冊；註冊與綁定也各有配額。"""
    client = _throttled_client(max_attempts=1)
    login = {"email": "a@example.com", "password": "wrong-password"}
    client.post("/api/v1/sessions", json=login)
    assert client.post("/api/v1/sessions", json=login).status_code == 429
    reg = {"email": "a@example.com", "password": "correct-horse-8", "name": "兒子"}
    assert client.post("/api/v1/guardians", json=reg).status_code == 201
    assert client.post("/api/v1/guardians", json=reg).status_code == 429
    assert client.post("/api/v1/device-bindings", json={"code": "nope"}).status_code == 404
    assert client.post("/api/v1/device-bindings", json={"code": "nope"}).status_code == 429


# --- 長輩帳密（✅ D-71 己-6）：POST /elder-sessions ---


def _paired_elder_with_account(svc, phone="0912345678", password="sunsun-8888"):
    from kinsun.accounts.models import ConsentBy

    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    svc.register_elder_account(elder.elder_id, phone, password)
    return elder


def test_elder_login_returns_session():
    svc = _service()
    elder = _paired_elder_with_account(svc)
    res = _client(svc).post(
        "/api/v1/elder-sessions", json={"phone": "0912-345-678", "password": "sunsun-8888"}
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["elder_id"] == elder.elder_id
    assert body["name"] == "阿公"
    assert len(body["token"]) >= 32


def test_elder_login_wrong_password_401():
    svc = _service()
    _paired_elder_with_account(svc)
    res = _client(svc).post(
        "/api/v1/elder-sessions", json={"phone": "0912345678", "password": "wrong-password"}
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_elder_login_not_paired_403():
    svc = _service()
    elder = svc.create_elder("U-son", "兒子", "阿公")  # 未掃碼配對
    svc.register_elder_account(elder.elder_id, "0912345678", "sunsun-8888")
    res = _client(svc).post(
        "/api/v1/elder-sessions", json={"phone": "0912345678", "password": "sunsun-8888"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "not_paired"


def test_elder_login_throttled_429():
    svc = _service()
    _paired_elder_with_account(svc)
    client = _client(svc, rate_limiter=SlidingWindowRateLimiter(2, 300.0))
    payload = {"phone": "0912345678", "password": "wrong-password"}
    assert client.post("/api/v1/elder-sessions", json=payload).status_code == 401
    assert client.post("/api/v1/elder-sessions", json=payload).status_code == 401
    res = client.post("/api/v1/elder-sessions", json=payload)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "too_many_requests"
