from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.reports.reminders import ReminderLog
from kinsun.safety.events import RiskEvent
from kinsun.safety.tiers import RiskTier
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from kinsun.web.auth import LineIdentity
from kinsun.web.routers import create_guardian_face_router
from tests.fakes import (
    FakeAccountStore,
    FakeConversationSummaryStore,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=TPE)
RECENT = (NOW - timedelta(days=5)).timestamp()
OLD = (NOW - timedelta(days=40)).timestamp()


class _FakeVerifier:
    def __init__(self, line_user_id="U-son"):
        self._line_user_id = line_user_id

    def verify(self, id_token):
        return LineIdentity(self._line_user_id, "兒子")


class _RiskEvents:
    def __init__(self, events):
        self._events = events

    def list_for_elder(self, elder_id):
        return self._events


class _Reminders:
    def __init__(self, logs):
        self._logs = logs

    def list_for_elder(self, elder_id):
        return self._logs


def _client(line_user_id, *, risks, reminders, bind_elder=True, summaries=None):
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    accounts = AccountService(
        repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c"
    )
    elder = accounts.create_elder("U-son", "兒子", "阿公")
    if bind_elder:
        from kinsun.accounts.models import Channel, ChannelBinding, PrincipalType

        repo.save_channel_binding(
            ChannelBinding(Channel.LINE, "U-elder", PrincipalType.ELDER, elder.elder_id, 0.0)
        )
    app = FastAPI()
    app.include_router(
        create_guardian_face_router(
            verifier=_FakeVerifier(line_user_id),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: NOW),
            clock=lambda: NOW,
            risk_events=_RiskEvents(risks),
            reminder_logs=_Reminders(reminders),
            summaries=summaries or FakeConversationSummaryStore(),
            appointment_hour=8,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), elder.elder_id


def _auth():
    return {"Authorization": "Bearer tok"}


def test_health_report_recent_only():
    risks = [
        RiskEvent("r1", "U-elder", RiskTier.L2, "昏倒", RECENT),
        RiskEvent("r0", "U-elder", RiskTier.L2, "舊事件", OLD),
    ]
    reminders = [
        ReminderLog("m1", "e", "medication", "早上用藥：A", RECENT),
        ReminderLog("m0", "e", "appointment", "舊提醒", OLD),
    ]
    client, elder_id = _client("U-son", risks=risks, reminders=reminders)
    res = client.get(f"/api/v1/elders/{elder_id}/health-report", headers=_auth())
    assert res.status_code == 200
    body = res.json()["data"]
    assert [e["reason"] for e in body["risk_events"]] == ["昏倒"]
    assert body["risk_events"][0]["tier"] == 2
    assert [r["content"] for r in body["reminders"]] == ["早上用藥：A"]


def test_health_report_rejects_unmanaged():
    client, elder_id = _client("U-stranger", risks=[], reminders=[])
    res = client.get(f"/api/v1/elders/{elder_id}/health-report", headers=_auth())
    assert res.status_code == 404


def test_health_report_requires_token():
    client, elder_id = _client("U-son", risks=[], reminders=[])
    assert client.get(f"/api/v1/elders/{elder_id}/health-report").status_code == 401


def test_health_report_unbound_elder_still_reports():
    # 會話主鍵通道中立後，報告以 elder_id 直查，長輩未綁 LINE 不影響內容。
    reminders = [ReminderLog("m1", "e", "medication", "早上用藥：A", RECENT)]
    client, elder_id = _client("U-son", risks=[], reminders=reminders, bind_elder=False)
    res = client.get(f"/api/v1/elders/{elder_id}/health-report", headers=_auth())
    assert res.status_code == 200
    assert res.json()["data"]["risk_events"] == []
    assert [r["content"] for r in res.json()["data"]["reminders"]] == ["早上用藥：A"]


# --- 每日摘要開放家屬（✅ D-09 己-3）---


def _summaries_store(rows):
    store = FakeConversationSummaryStore()
    for elder_id, date, content in rows:
        store.save(elder_id, date, content)
    return store


def test_daily_summaries_listed_newest_first():
    summaries = _summaries_store([])
    client, elder_id = _client("U-son", risks=[], reminders=[], summaries=summaries)
    summaries.save(elder_id, "2026-07-28", "阿公聊了孫子，心情不錯")
    summaries.save(elder_id, "2026-07-29", "阿公說膝蓋有點痠")
    res = client.get(f"/api/v1/elders/{elder_id}/daily-summaries", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert [(s["date"], s["content"]) for s in body["data"]] == [
        ("2026-07-29", "阿公說膝蓋有點痠"),
        ("2026-07-28", "阿公聊了孫子，心情不錯"),
    ]


def test_daily_summaries_limit():
    summaries = _summaries_store([])
    client, elder_id = _client("U-son", risks=[], reminders=[], summaries=summaries)
    for day in ("2026-07-27", "2026-07-28", "2026-07-29"):
        summaries.save(elder_id, day, f"{day} 的摘要")
    res = client.get(f"/api/v1/elders/{elder_id}/daily-summaries?limit=1", headers=_auth())
    assert [s["date"] for s in res.json()["data"]] == ["2026-07-29"]


def test_daily_summaries_scope_guard_404_for_stranger():
    client, elder_id = _client("U-son", risks=[], reminders=[])
    stranger, _ = _client("U-stranger", risks=[], reminders=[])
    res = stranger.get(f"/api/v1/elders/{elder_id}/daily-summaries", headers=_auth())
    assert res.status_code == 404
