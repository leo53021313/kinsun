from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import (
    ApiToken,
    Channel,
    ChannelBinding,
    Consent,
    ConsentBy,
    Elder,
    ElderAccount,
    ElderGuardian,
    Guardian,
    Invite,
    InviteRole,
    PrincipalType,
    Role,
)
from kinsun.accounts.store import FakeAccountStore
from kinsun.appointments.models import Appointment
from kinsun.appointments.store import FakeAppointmentStore
from kinsun.medications.models import Medication, MedicationSlot
from kinsun.medications.store import FakeMedicationStore
from kinsun.memory.models import MemoryItem
from kinsun.reports.reminders import FakeReminderLogStore
from kinsun.reports.summaries import FakeConversationSummaryStore
from kinsun.safety.deliveries import FakeRiskNotificationLogStore
from kinsun.safety.tiers import RiskTier
from kinsun.web.routers import create_admin_router
from tests.fakes import FakeTraceStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 3, 12, 0, tzinfo=TPE)
TODAY_TS = datetime(2026, 7, 3, 8, 0, tzinfo=TPE).timestamp()


class _StubRiskEvents:
    """只提供告警計數的替身。"""

    def __init__(self, failsafe_count: int) -> None:
        self._count = failsafe_count
        self.cutoffs: list[float] = []

    def count_failsafe_since(self, cutoff: float) -> int:
        self.cutoffs.append(cutoff)
        return self._count


class _FakeLongTerm:
    """LongTermStore 替身：只實作 admin 觀測用到的 list_for_elder。"""

    def __init__(self) -> None:
        self.items: dict[str, list[MemoryItem]] = {}

    def list_for_elder(self, elder_id: str, *, limit: int = 50) -> list[MemoryItem]:
        return self.items.get(elder_id, [])[:limit]


def _client(
    traces=None,
    *,
    admin_api_key="secret",
    risk_events=None,
    account_store=None,
    med_store=None,
    appt_store=None,
    reminder_logs=None,
    summaries=None,
    long_term=None,
    deliveries=None,
):
    app = FastAPI()
    app.include_router(
        create_admin_router(
            admin_api_key=admin_api_key,
            traces=traces or FakeTraceStore(),
            clock=lambda: NOW,
            risk_events=risk_events,
            account_store=account_store or FakeAccountStore(),
            med_store=med_store or FakeMedicationStore(),
            appt_store=appt_store or FakeAppointmentStore(),
            reminder_logs=reminder_logs or FakeReminderLogStore(),
            summaries=summaries or FakeConversationSummaryStore(),
            long_term=long_term or _FakeLongTerm(),
            deliveries=deliveries or FakeRiskNotificationLogStore(),
        ),
        prefix="/api/v1/admin",
    )
    return TestClient(app)


def _auth():
    return {"X-Admin-Key": "secret"}


def test_missing_key_returns_401():
    assert _client().get("/api/v1/admin/overview").status_code == 401


def test_wrong_key_returns_401():
    res = _client().get("/api/v1/admin/overview", headers={"X-Admin-Key": "wrong"})
    assert res.status_code == 401


def test_unconfigured_key_returns_503():
    res = _client(admin_api_key="").get("/api/v1/admin/overview", headers=_auth())
    assert res.status_code == 503


def test_overview_shape():
    traces = FakeTraceStore()
    traces.seed_turn("e1", "user", "hi", TODAY_TS)
    res = _client(traces).get("/api/v1/admin/overview", headers=_auth())
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["turn_count"] == 1
    assert body["active_elder_count"] == 1
    assert {s["stage"] for s in body["stages"]} == {"asr", "llm", "tts", "round_trip"}
    assert all("p50_latency_ms" in s and "p95_latency_ms" in s for s in body["stages"])
    assert isinstance(body["hourly_turns"], list)
    assert isinstance(body["generated_at"], float)
    assert body["alerts"] == []  # 未注入 risk_events 時不告警


def test_overview_alert_when_failsafe_over_threshold():
    """✅ D-31＋D-66（甲-5）：近 1 小時 fail-safe 事件達門檻 → overview 帶告警。"""
    stub = _StubRiskEvents(failsafe_count=3)
    res = _client(risk_events=stub).get("/api/v1/admin/overview", headers=_auth())
    body = res.json()["data"]
    assert body["alerts"] == [{"kind": "risk_classifier_failure", "count": 3, "window_minutes": 60}]
    assert stub.cutoffs == [(NOW - timedelta(minutes=60)).timestamp()]


def test_overview_no_alert_below_threshold():
    stub = _StubRiskEvents(failsafe_count=2)
    res = _client(risk_events=stub).get("/api/v1/admin/overview", headers=_auth())
    assert res.json()["data"]["alerts"] == []


def test_list_elders():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    traces.seed_binding("U1", "e1")
    traces.seed_turn("e1", "user", "hi", TODAY_TS)
    res = _client(traces).get("/api/v1/admin/elders", headers=_auth())
    assert res.status_code == 200
    assert res.json()["data"] == [
        {
            "elder_id": "e1",
            "name": "阿公",
            "bound_channels": "line",
            "last_active_at": TODAY_TS,
        }
    ]


def test_messages_feed_desc_with_after():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    traces.seed_turn("e1", "user", "早安", TODAY_TS)
    traces.seed_risk("e1", 2, "頭暈", TODAY_TS + 10, trace_id="t1")
    res = _client(traces).get(
        "/api/v1/admin/messages", params={"after": TODAY_TS - 1}, headers=_auth()
    )
    assert res.status_code == 200
    messages = res.json()["data"]
    assert [m["kind"] for m in messages] == ["risk", "turn"]
    assert messages[0]["trace_id"] == "t1"
    assert messages[0]["tier"] == 2


def test_messages_limit_validation():
    res = _client().get("/api/v1/admin/messages", params={"limit": 9999}, headers=_auth())
    assert res.status_code == 422


def test_messages_before_cursor_and_meta():
    """✅ D-29（乙-6）：before 回翻歷史＋信封 meta（limit／before／after／has_more）。"""
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    traces.seed_turn("e1", "user", "一", TODAY_TS)
    traces.seed_turn("e1", "user", "二", TODAY_TS + 10)
    traces.seed_turn("e1", "user", "三", TODAY_TS + 20)
    res = _client(traces).get(
        "/api/v1/admin/messages",
        params={"before": TODAY_TS + 20, "limit": 1},
        headers=_auth(),
    )
    body = res.json()
    assert [m["content"] for m in body["data"]] == ["二"]
    assert body["meta"] == {
        "limit": 1,
        "before": TODAY_TS + 20,
        "after": None,
        "has_more": True,
    }
    # 回翻到底：has_more=False。
    res = _client(traces).get(
        "/api/v1/admin/messages",
        params={"before": TODAY_TS + 5, "limit": 10},
        headers=_auth(),
    )
    body = res.json()
    assert [m["content"] for m in body["data"]] == ["一"]
    assert body["meta"]["has_more"] is False


def test_timeline_for_elder():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    traces.seed_turn("e1", "user", "早安", TODAY_TS)
    res = _client(traces).get(
        "/api/v1/admin/elders/e1/timeline", params={"date": "2026-07-03"}, headers=_auth()
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["name"] == "阿公"
    assert body["date"] == "2026-07-03"
    assert [i["kind"] for i in body["items"]] == ["turn"]


def test_timeline_unknown_elder_404():
    res = _client().get("/api/v1/admin/elders/nope/timeline", headers=_auth())
    assert res.status_code == 404


def test_timeline_bad_date_400():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    res = _client(traces).get(
        "/api/v1/admin/elders/e1/timeline", params={"date": "07/03"}, headers=_auth()
    )
    assert res.status_code == 400


def test_trace_detail_and_404():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公")
    traces.seed_binding("U1", "e1")
    traces.now = TODAY_TS
    traces.record_asr_call(
        trace_id="t1",
        line_user_id="U1",
        status="ok",
        latency_ms=5,
        transcript="嗨",
        source_audio_url="",
        error_message="",
    )
    ok = _client(traces).get("/api/v1/admin/traces/t1", headers=_auth())
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["elder_name"] == "阿公"
    assert body["asr_call"]["transcript"] == "嗨"
    assert body["webhook_event"] is None
    missing = _client(traces).get("/api/v1/admin/traces/nope", headers=_auth())
    assert missing.status_code == 404


def test_elder_reminders_shape():
    """spec 2026-07-12 §3.3：提醒設定分頁——用藥主檔＋回診＋近期發送紀錄。"""
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    meds = FakeMedicationStore()
    meds.save(Medication("m1", "e1", "降血壓藥", (MedicationSlot.MORNING,)))
    appts = FakeAppointmentStore()
    appts.save(Appointment("a1", "e1", "2026-07-20", "心臟科回診"))
    logs = FakeReminderLogStore()
    logs.record("e1", "medication", "早上用藥：降血壓藥")
    res = _client(
        account_store=accounts, med_store=meds, appt_store=appts, reminder_logs=logs
    ).get("/api/v1/admin/elders/e1/reminders", headers=_auth())
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["medications"] == [{"medication_id": "m1", "name": "降血壓藥", "slots": ["morning"]}]
    assert body["appointments"][0]["label"] == "心臟科回診"
    assert body["reminder_logs"][0]["kind"] == "medication"


def test_elder_detail_endpoints_404_for_unknown_elder():
    for path in ("reminders", "memory", "account", "risk-notifications"):
        res = _client().get(f"/api/v1/admin/elders/nope/{path}", headers=_auth())
        assert res.status_code == 404, path


def test_elder_memory_shape():
    """spec 2026-07-12 §3.3：記憶與摘要分頁——長期記憶＋每日摘要。"""
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    long_term = _FakeLongTerm()
    long_term.items["e1"] = [MemoryItem(text="喜歡下棋", provenance="長輩自述", date="2026-07-01")]
    summaries = FakeConversationSummaryStore()
    summaries.save("e1", "2026-07-11", "阿公今天心情不錯。")
    res = _client(account_store=accounts, long_term=long_term, summaries=summaries).get(
        "/api/v1/admin/elders/e1/memory", headers=_auth()
    )
    body = res.json()["data"]
    assert body["memories"] == [{"text": "喜歡下棋", "provenance": "長輩自述", "date": "2026-07-01"}]
    assert body["summaries"][0]["date"] == "2026-07-11"


def test_elder_account_shape():
    """spec 2026-07-12 §3.3：帳號與綁定分頁——排查「為什麼登不進去」。"""
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    accounts.save_guardian(Guardian("g1", "小明"))
    accounts.save_elder_guardian(ElderGuardian("e1", "g1", Role.PRIMARY, 1))
    accounts.save_invite(
        Invite("CODE1", "e1", InviteRole.ELDER, NOW.timestamp() + 60, 5, 0, None)
    )
    accounts.save_consent(Consent("e1", ConsentBy.PROXY, "v1", 1.0, None))
    accounts.save_channel_binding(
        ChannelBinding(Channel.APP, "dev1", PrincipalType.ELDER, "e1", 1.0)
    )
    accounts.save_elder_account(ElderAccount("e1", "0912345678", "hash", 1.0))
    accounts.save_api_token(ApiToken("h1", PrincipalType.ELDER, "e1", 2.0))
    res = _client(account_store=accounts).get("/api/v1/admin/elders/e1/account", headers=_auth())
    body = res.json()["data"]
    assert body["bindings"][0]["channel"] == "app"
    assert body["invites"][0] == {
        "code": "CODE1",
        "role": "elder",
        "status": "active",
        "expires_at": NOW.timestamp() + 60,
        "attempts": 0,
    }
    assert body["consent"]["consent_by"] == "proxy"
    assert body["has_password_account"] is True
    assert body["phone"] == "0912345678"
    assert body["tokens"] == [{"created_at": 2.0}]
    assert body["guardians"][0]["name"] == "小明"


def test_elder_account_invite_status_expired():
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    accounts.save_invite(
        Invite("OLD1", "e1", InviteRole.ELDER, NOW.timestamp() - 60, 5, 0, None)
    )
    res = _client(account_store=accounts).get("/api/v1/admin/elders/e1/account", headers=_auth())
    assert res.json()["data"]["invites"][0]["status"] == "expired"


def test_elder_risk_notifications_with_guardian_name():
    """spec 2026-07-12 §3.3：危急通知分頁——每位家屬送達成功／失敗。"""
    accounts = FakeAccountStore()
    accounts.save_elder(Elder("e1", "阿公"))
    accounts.save_guardian(Guardian("g1", "小明"))
    deliveries = FakeRiskNotificationLogStore()
    deliveries.record("e1", "g1", RiskTier.L2, delivered=True)
    res = _client(account_store=accounts, deliveries=deliveries).get(
        "/api/v1/admin/elders/e1/risk-notifications", headers=_auth()
    )
    item = res.json()["data"][0]
    assert item["guardian_name"] == "小明"
    assert item["tier"] == 2
    assert item["delivered"] is True
