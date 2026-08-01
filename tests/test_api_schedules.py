"""排程 API：CRUD、授權守門與輸入驗證。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from kinsun.web.auth import LineIdentity
from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers import create_guardian_face_router
from tests.fakes import (
    FakeAccountStore,
    FakeConversationSummaryStore,
    FakeReminderLogStore,
    FakeRiskEventStore,
)

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=TZ)


class _Verifier:
    def verify(self, id_token: str) -> LineIdentity:
        return LineIdentity(id_token, "兒子")


def _make_client(*, now: datetime = NOW, appointment_hour: int = 8):
    """⚠️ `now` 一律帶著 `Asia/Taipei` 進來，不讀執行機器的環境時區。

    回診「前一天」那段推算只在 UTC 以東的時區出錯（12 §9 F-16），跟著機器時區跑的
    測試會在 UTC 的 CI 上一路綠燈。
    """
    store = FakeAccountStore()
    accounts = AccountService(store, clock=lambda: now)
    elder = accounts.create_elder("U-son", "兒子", "阿嬤")
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_guardian_face_router(
            verifier=_Verifier(),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: now),
            clock=lambda: now,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
            summaries=FakeConversationSummaryStore(),
            appointment_hour=appointment_hour,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), elder.elder_id


@pytest.fixture
def client_and_elder():
    return _make_client()


AUTH = {"Authorization": "Bearer U-son"}


def _post(client, elder_id, **overrides):
    body = {
        "kind": "medication",
        "title": "血壓藥",
        "occurrences": [{"repeat": "daily", "time": "08:00"}],
    }
    body.update(overrides)
    return client.post(f"/api/v1/elders/{elder_id}/schedules", json=body, headers=AUTH)


def test_create_and_list(client_and_elder):
    client, elder_id = client_and_elder
    created = _post(client, elder_id)
    assert created.status_code == 201
    payload = created.json()["data"]
    assert payload["title"] == "血壓藥"
    assert payload["kind"] == "medication"
    assert payload["created_by"] == "guardian"
    assert [o["time"] for o in payload["occurrences"]] == ["08:00"]

    listed = client.get(f"/api/v1/elders/{elder_id}/schedules", headers=AUTH)
    assert [g["group_id"] for g in listed.json()["data"]] == [payload["group_id"]]


def test_create_appointment_with_event_time(client_and_elder):
    client, elder_id = client_and_elder
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[
            {"repeat": "once", "date": "2026-07-29", "time": "08:00"},
            {"repeat": "once", "date": "2026-07-30", "time": "08:00"},
        ],
        event_date="2026-07-30",
        event_time="10:30",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert len(data["occurrences"]) == 2
    assert data["event_at"] == datetime(2026, 7, 30, 10, 30, tzinfo=TZ).timestamp()
    # 沒有東西要告訴家屬時 meta 維持 null，不平白多一則雜訊要 UI 去分辨。
    assert created.json()["meta"] is None


def test_appointment_day_before_is_recomputed_not_taken_from_the_client():
    """回診的「前一天」由**後端**從 `event_date` 重算，client 送什麼都不算數。

    ⚠️ 這條釘的是一個真的進過資料庫的 bug（12 §9 F-16）：三份前端共用的那段推算
    ——`new Date("2026-08-05T00:00:00")`（依**本地時區**解析）減 86400000 毫秒、再用
    `toISOString()`（**UTC**）取日期——在 `Asia/Taipei` 會算出 **2026-08-03**，提醒提早
    兩天響。下面 `occurrences` 送的正是 `app/`／`frontend/` 在台灣實際會送出的內容。

    ⚠️ **時區必須釘死在斷言裡**：這個 bug 在 UTC 與美洲時區都算得對，跟著執行機器
    的環境時區跑的測試會在 CI 上一路綠燈——它就是這樣活了六天沒被發現。
    """
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 12, 0, tzinfo=TZ))
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[
            {"repeat": "once", "date": "2026-08-03", "time": "08:00"},  # 前端算錯的那一天
            {"repeat": "once", "date": "2026-08-05", "time": "08:00"},
        ],
        event_date="2026-08-05",
    )
    assert created.status_code == 201
    assert sorted(o["scheduled_at"] for o in created.json()["data"]["occurrences"]) == [
        datetime(2026, 8, 4, 8, 0, tzinfo=TZ).timestamp(),
        datetime(2026, 8, 5, 8, 0, tzinfo=TZ).timestamp(),
    ]


def test_appointment_reminder_hour_comes_from_settings_not_from_the_client():
    """鐘點也由後端決定：前端寫死 08:00，`APPOINTMENT_REMINDER_HOUR` 改了它不會跟。"""
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 12, 0, tzinfo=TZ), appointment_hour=9)
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[{"repeat": "once", "date": "2026-08-05", "time": "08:00"}],
        event_date="2026-08-05",
    )
    assert created.status_code == 201
    assert sorted(o["scheduled_at"] for o in created.json()["data"]["occurrences"]) == [
        datetime(2026, 8, 4, 9, 0, tzinfo=TZ).timestamp(),
        datetime(2026, 8, 5, 9, 0, tzinfo=TZ).timestamp(),
    ]


def test_tomorrows_appointment_set_in_the_afternoon_still_creates_the_day_of_reminder():
    """下午設明天的回診：「前一天 08:00」已經過了，略過它、當天那顆照建。

    原本整筆會被服務層擋成「那個時間已經過去了」——家屬填的明明是明天。
    """
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 15, 0, tzinfo=TZ))
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[
            {"repeat": "once", "date": "2026-07-25", "time": "08:00"},
            {"repeat": "once", "date": "2026-07-26", "time": "08:00"},
        ],
        event_date="2026-07-26",
    )
    assert created.status_code == 201
    occurrences = created.json()["data"]["occurrences"]
    assert [o["scheduled_at"] for o in occurrences] == [
        datetime(2026, 7, 26, 8, 0, tzinfo=TZ).timestamp()
    ]


def test_skipping_the_day_before_reminder_is_told_to_the_guardian():
    """少建一顆鬧鐘不可以靜默：回應要帶著能直接顯示給家屬看的繁中人話。"""
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 15, 0, tzinfo=TZ))
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[{"repeat": "once", "date": "2026-07-26", "time": "08:00"}],
        event_date="2026-07-26",
    )
    warnings = created.json()["meta"]["warnings"]
    assert len(warnings) == 1
    assert "前一天" in warnings[0]
    assert "08:00" in warnings[0]


def test_appointment_whose_reminders_have_all_passed_says_so_in_plain_chinese():
    """今天下午才設今天的回診：兩顆都過去了，明說是回診日的問題，不含糊帶過。"""
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 15, 0, tzinfo=TZ))
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[{"repeat": "once", "date": "2026-07-25", "time": "08:00"}],
        event_date="2026-07-25",
    )
    assert created.status_code == 400
    body = created.json()["error"]
    assert body["code"] == "invalid_schedule"
    assert "回診" in body["message"] and "已經過了" in body["message"]


def test_update_also_recomputes_the_day_before(client_and_elder):
    """編輯走的是同一支前端函式，接管也必須同時涵蓋 PUT。"""
    client, elder_id = client_and_elder
    group_id = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[{"repeat": "once", "date": "2026-07-30", "time": "08:00"}],
        event_date="2026-07-30",
    ).json()["data"]["group_id"]
    updated = client.put(
        f"/api/v1/elders/{elder_id}/schedules/{group_id}",
        json={
            "kind": "appointment",
            "title": "心臟科回診",
            "occurrences": [
                {"repeat": "once", "date": "2026-08-03", "time": "08:00"},  # 又是算錯的那天
                {"repeat": "once", "date": "2026-08-05", "time": "08:00"},
            ],
            "event_date": "2026-08-05",
        },
        headers=AUTH,
    )
    assert updated.status_code == 200
    assert sorted(o["scheduled_at"] for o in updated.json()["data"]["occurrences"]) == [
        datetime(2026, 8, 4, 8, 0, tzinfo=TZ).timestamp(),
        datetime(2026, 8, 5, 8, 0, tzinfo=TZ).timestamp(),
    ]


def test_appointment_without_an_event_date_keeps_the_client_occurrences():
    """沒給回診日就沒得重算——這條路徑維持原樣，接管不可以順手改掉它。"""
    client, elder_id = _make_client(now=datetime(2026, 7, 25, 12, 0, tzinfo=TZ))
    created = _post(
        client,
        elder_id,
        kind="appointment",
        title="心臟科回診",
        occurrences=[{"repeat": "once", "date": "2026-08-05", "time": "14:30"}],
    )
    assert created.status_code == 201
    assert [o["scheduled_at"] for o in created.json()["data"]["occurrences"]] == [
        datetime(2026, 8, 5, 14, 30, tzinfo=TZ).timestamp()
    ]


def test_list_can_filter_by_kind(client_and_elder):
    client, elder_id = client_and_elder
    _post(client, elder_id)
    _post(client, elder_id, kind="custom", title="散步")
    listed = client.get(f"/api/v1/elders/{elder_id}/schedules?kind=custom", headers=AUTH)
    assert [g["title"] for g in listed.json()["data"]] == ["散步"]


def test_update_replaces_occurrences_and_keeps_group(client_and_elder):
    client, elder_id = client_and_elder
    group_id = _post(client, elder_id).json()["data"]["group_id"]
    updated = client.put(
        f"/api/v1/elders/{elder_id}/schedules/{group_id}",
        json={
            "kind": "medication",
            "title": "血壓藥（新）",
            "occurrences": [
                {"repeat": "daily", "time": "07:30"},
                {"repeat": "daily", "time": "21:00"},
            ],
        },
        headers=AUTH,
    )
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["group_id"] == group_id
    assert data["title"] == "血壓藥（新）"
    assert sorted(o["time"] for o in data["occurrences"]) == ["07:30", "21:00"]


def test_delete_removes_it_from_the_list(client_and_elder):
    client, elder_id = client_and_elder
    group_id = _post(client, elder_id).json()["data"]["group_id"]
    assert (
        client.delete(f"/api/v1/elders/{elder_id}/schedules/{group_id}", headers=AUTH).status_code
        == 204
    )
    assert client.get(f"/api/v1/elders/{elder_id}/schedules", headers=AUTH).json()["data"] == []


def test_unknown_group_is_404(client_and_elder):
    client, elder_id = client_and_elder
    assert (
        client.delete(f"/api/v1/elders/{elder_id}/schedules/nope", headers=AUTH).status_code == 404
    )


def test_blank_title_is_rejected(client_and_elder):
    client, elder_id = client_and_elder
    assert _post(client, elder_id, title="   ").status_code == 400


def test_unknown_kind_is_rejected(client_and_elder):
    client, elder_id = client_and_elder
    assert _post(client, elder_id, kind="exercise").status_code == 400


def test_empty_occurrences_is_rejected(client_and_elder):
    client, elder_id = client_and_elder
    assert _post(client, elder_id, occurrences=[]).status_code == 400


def test_malformed_time_is_rejected(client_and_elder):
    client, elder_id = client_and_elder
    bad = _post(client, elder_id, occurrences=[{"repeat": "daily", "time": "25:99"}])
    assert bad.status_code == 400


def test_past_one_off_is_rejected(client_and_elder):
    client, elder_id = client_and_elder
    response = _post(
        client,
        elder_id,
        kind="custom",
        title="來不及了",
        occurrences=[{"repeat": "once", "date": "2020-01-01", "time": "10:00"}],
    )
    assert response.status_code == 400


def test_missing_token_is_401(client_and_elder):
    client, elder_id = client_and_elder
    assert client.get(f"/api/v1/elders/{elder_id}/schedules").status_code == 401


def test_another_guardians_elder_is_404(client_and_elder):
    # 不是自己管的長輩一律 404，不洩漏「這個 id 存在」。
    client, elder_id = client_and_elder
    other = {"Authorization": "Bearer U-stranger"}
    assert client.get(f"/api/v1/elders/{elder_id}/schedules", headers=other).status_code == 404


def test_update_rejects_a_different_kind_instead_of_silently_ignoring_it(client_and_elder):
    """改分類不是靜默無效，是明確 400（A-09 修正版，2026-07-29）。

    ⚠️ **`replace_group` 不改 kind 是刻意的**（見其 docstring：「改內容不該讓一筆
    家屬設的藥變成長輩設的，也不該讓用藥變成回診」），所以正解不是讓 kind 可改。

    真正的缺陷在契約說謊：`ScheduleIn.kind` 是**必填**卻永遠被忽略，家屬把用藥改成
    回診會拿到 200 OK 與一筆完全沒變的資料——這是「答應了卻沒做」那一類的錯，而
    UI 沒有任何理由懷疑它。改成 400 讓呼叫端知道要改分類得刪掉重建。
    """
    client, elder_id = client_and_elder
    group_id = _post(client, elder_id).json()["data"]["group_id"]
    res = client.put(
        f"/api/v1/elders/{elder_id}/schedules/{group_id}",
        json={
            "kind": "appointment",  # 原本是 medication
            "title": "血壓藥",
            "occurrences": [{"repeat": "daily", "time": "07:30"}],
        },
        headers=AUTH,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "kind_not_changeable"
    # 而且原本那組必須原封不動——半套的修改比不修改更難察覺。
    listed = client.get(f"/api/v1/elders/{elder_id}/schedules", headers=AUTH)
    assert listed.json()["data"][0]["kind"] == "medication"


def test_update_with_the_same_kind_still_works(client_and_elder):
    """送對的 kind 照舊——這是既有行為，不可被上面那條擋掉。"""
    client, elder_id = client_and_elder
    group_id = _post(client, elder_id).json()["data"]["group_id"]
    res = client.put(
        f"/api/v1/elders/{elder_id}/schedules/{group_id}",
        json={
            "kind": "medication",
            "title": "血壓藥（新）",
            "occurrences": [{"repeat": "daily", "time": "07:30"}],
        },
        headers=AUTH,
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "血壓藥（新）"
