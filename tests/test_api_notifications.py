"""App 內通知讀取端點：家屬面 `/notifications` 與長輩面 `/elder-notifications`。

為什麼要有長輩面（X-01，2026-07-29 全面自動化測試）：提醒送出＝落一筆
`app_notifications`（`AppOutboundChannel`），但先前只有家屬讀得到，且只查家屬自己的
`external_id`——寫給長輩的那一列**誰都讀不到**。用藥／回診／主動關懷三種提醒對
「長輩與家屬皆只用 App」的家庭等於不存在（PRD US-B2、BDD R4）。
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.notifications.store import FakeAppNotificationStore
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


def _client(svc, notifications=None):
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_auth_router(accounts=svc, notifications=notifications), prefix="/api/v1"
    )
    return TestClient(app)


def _family(svc, *, elder_name="王阿嬤"):
    """建一組家屬＋長輩＋長輩裝置綁定，回 (guardian_id, guardian_token, elder_id, elder_token)。"""
    guardian, guardian_token = svc.register_guardian_account(
        f"g{elder_name}@example.com", "correct-horse-8", "兒子"
    )
    elder = svc.create_elder_for_guardian(guardian.guardian_id, elder_name)
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    _, elder_token = svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    return guardian.guardian_id, guardian_token, elder.elder_id, elder_token


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── 長輩讀自己的提醒（X-01 的核心）────────────────────────────────


def test_elder_reads_own_reminder():
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    notifications = FakeAppNotificationStore()
    notifications.record(svc.app_external_id_of_elder(elder_id), "阿嬤，早上該吃藥囉：血壓藥")

    res = _client(svc, notifications).get(
        "/api/v1/elder-notifications", headers=_bearer(elder_token)
    )

    assert res.status_code == 200
    items = res.json()["data"]
    assert [i["content"] for i in items] == ["阿嬤，早上該吃藥囉：血壓藥"]
    assert "created_at" in items[0]


def test_elder_reads_only_own_notifications():
    """越權：兩位長輩各有提醒，彼此讀不到對方的。"""
    svc = _service()
    _, _, elder_a, token_a = _family(svc, elder_name="王阿嬤")
    _, _, elder_b, _ = _family(svc, elder_name="李阿公")
    notifications = FakeAppNotificationStore()
    notifications.record(svc.app_external_id_of_elder(elder_a), "阿嬤的藥")
    notifications.record(svc.app_external_id_of_elder(elder_b), "阿公的藥")

    res = _client(svc, notifications).get("/api/v1/elder-notifications", headers=_bearer(token_a))

    assert [i["content"] for i in res.json()["data"]] == ["阿嬤的藥"]


def test_elder_notifications_newest_first():
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    notifications = FakeAppNotificationStore()
    external_id = svc.app_external_id_of_elder(elder_id)
    for content in ("早上的藥", "中午的藥", "晚上的藥"):
        notifications.record(external_id, content)

    res = _client(svc, notifications).get(
        "/api/v1/elder-notifications", headers=_bearer(elder_token)
    )

    assert [i["content"] for i in res.json()["data"]] == ["晚上的藥", "中午的藥", "早上的藥"]


def test_elder_without_notifications_gets_empty_list():
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, FakeAppNotificationStore()).get(
        "/api/v1/elder-notifications", headers=_bearer(elder_token)
    )

    assert res.status_code == 200
    assert res.json()["data"] == []


def test_elder_notifications_without_store_gets_empty_list():
    """通知 store 未配置（如精簡部署）時回空陣列，不是 500。"""
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, None).get("/api/v1/elder-notifications", headers=_bearer(elder_token))

    assert res.status_code == 200
    assert res.json()["data"] == []


# ── 認證邊界 ──────────────────────────────────────────────────


def test_guardian_token_cannot_read_elder_notifications():
    svc = _service()
    _, guardian_token, _, _ = _family(svc)

    res = _client(svc, FakeAppNotificationStore()).get(
        "/api/v1/elder-notifications", headers=_bearer(guardian_token)
    )

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_token"


def test_missing_token_rejected():
    svc = _service()
    res = _client(svc, FakeAppNotificationStore()).get("/api/v1/elder-notifications")
    assert res.status_code == 401


def test_bogus_token_rejected():
    svc = _service()
    res = _client(svc, FakeAppNotificationStore()).get(
        "/api/v1/elder-notifications", headers=_bearer("not-a-real-token")
    )
    assert res.status_code == 401


# ── 家屬面不受影響（回歸）──────────────────────────────────────


def test_guardian_notifications_still_work():
    svc = _service()
    guardian_id, guardian_token, _, _ = _family(svc)
    notifications = FakeAppNotificationStore()
    for external_id in svc.app_external_ids_of_guardian(guardian_id):
        notifications.record(external_id, "阿嬤剛剛說不舒服")

    res = _client(svc, notifications).get("/api/v1/notifications", headers=_bearer(guardian_token))

    assert res.status_code == 200
    assert [i["content"] for i in res.json()["data"]] == ["阿嬤剛剛說不舒服"]


def test_elder_token_cannot_read_guardian_notifications():
    svc = _service()
    _, _, _, elder_token = _family(svc)

    res = _client(svc, FakeAppNotificationStore()).get(
        "/api/v1/notifications", headers=_bearer(elder_token)
    )

    assert res.status_code == 401
