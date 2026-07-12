from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _client(traces=None, *, admin_api_key="secret", risk_events=None):
    app = FastAPI()
    app.include_router(
        create_admin_router(
            admin_api_key=admin_api_key,
            traces=traces or FakeTraceStore(),
            clock=lambda: NOW,
            risk_events=risk_events,
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
