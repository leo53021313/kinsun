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


@pytest.fixture
def client_and_elder():
    store = FakeAccountStore()
    accounts = AccountService(store, clock=lambda: NOW)
    elder = accounts.create_elder("U-son", "兒子", "阿嬤")
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_guardian_face_router(
            verifier=_Verifier(),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: NOW),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
            summaries=FakeConversationSummaryStore(),
        ),
        prefix="/api/v1",
    )
    return TestClient(app), elder.elder_id


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
