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
from kinsun.notifications.models import NotificationSeverity
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


# ── 呈現分級（2026-08-01 Leo 裁決）──────────────────────────────


def test_notifications_expose_severity_so_the_client_can_tell_them_apart():
    """API 必須把 severity 送出去——前端拿到的若只有一段文字，「跌倒了」與
    「該吃藥了」在畫面上就長得一模一樣（這正是本次要修的症狀）。

    ⚠️ 鍵名與 kinsun-shared/types.ts::AppNotification 完全一致（snake_case，
    前後端同名，AGENTS.md 命名規範）。
    """
    svc = _service()
    _, _, elder_id, elder_token = _family(svc)
    notifications = FakeAppNotificationStore()
    external_id = svc.app_external_id_of_elder(elder_id)
    notifications.record(external_id, "阿嬤，早上該吃藥囉：血壓藥")
    notifications.record(
        external_id, "王阿嬤剛剛說：「我跌倒了」", severity=NotificationSeverity.ALERT
    )

    res = _client(svc, notifications).get(
        "/api/v1/elder-notifications", headers=_bearer(elder_token)
    )

    assert res.status_code == 200
    # 最近先：警報那則排在前面。
    assert [(i["content"], i["severity"]) for i in res.json()["data"]] == [
        ("王阿嬤剛剛說：「我跌倒了」", "alert"),
        ("阿嬤，早上該吃藥囉：血壓藥", "notice"),
    ]


def test_severity_on_the_wire_is_the_bare_literal():
    """JSON 送出去的必須是 `"alert"` 這個字面值，前端才比對得到。

    ⚠️ **這條測試釘的是「線上的值」，不是 handler 寫 `.value` 或寫裸 enum**
    （2026-08-01 變異驗證的實測結論，不是推測）：把 handler 的 `n.severity.value`
    改成 `n.severity`，本檔全部測試仍然全綠——`NotificationSeverity` 是 `StrEnum`，
    `json.dumps` 與 FastAPI 的 `jsonable_encoder` 對它的輸出都是 `"alert"`
    （兩者皆已直接實測）。也就是說**那是一個等價變異**，任何在 JSON 反序列化
    之後做的型別斷言（如 `type(x) is str`）都必然為真、零鑑別力，故刻意不寫。

    `.value` 仍留在 handler 裡，理由是明確與跨層一致（store 層寫入時也用
    `.value`），不是因為有測試守著它。改用別的序列化器（如 Pydantic 模型）時，
    這條測試會是那時唯一還算數的防線——它驗的是最終送到前端的位元組。
    """
    svc = _service()
    guardian_id, guardian_token, _, _ = _family(svc)
    notifications = FakeAppNotificationStore()
    for external_id in svc.app_external_ids_of_guardian(guardian_id):
        notifications.record(external_id, "跌倒了", severity=NotificationSeverity.ALERT)

    res = _client(svc, notifications).get("/api/v1/notifications", headers=_bearer(guardian_token))

    # 直接比對原始位元組：走 `res.json()` 讀不出「線上長什麼樣」這件事。
    assert '"severity":"alert"' in res.text.replace(" ", "")


def test_guardian_notifications_default_to_notice():
    """家屬面的一般通知（每日摘要、提醒轉知）維持 notice，不可整批變紅。"""
    svc = _service()
    guardian_id, guardian_token, _, _ = _family(svc)
    notifications = FakeAppNotificationStore()
    for external_id in svc.app_external_ids_of_guardian(guardian_id):
        notifications.record(external_id, "今天阿嬤心情不錯")

    res = _client(svc, notifications).get("/api/v1/notifications", headers=_bearer(guardian_token))

    assert [i["severity"] for i in res.json()["data"]] == ["notice"]
