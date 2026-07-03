from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.admin_api import create_admin_api_router
from tests.fakes import FakeTraceStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 3, 12, 0, tzinfo=TPE)
TODAY_TS = datetime(2026, 7, 3, 8, 0, tzinfo=TPE).timestamp()


def _client(traces=None, *, admin_api_key="secret"):
    app = FastAPI()
    app.include_router(
        create_admin_api_router(
            admin_api_key=admin_api_key,
            traces=traces or FakeTraceStore(),
            clock=lambda: NOW,
        )
    )
    return TestClient(app)


def _auth():
    return {"X-Admin-Key": "secret"}


def test_missing_key_returns_401():
    assert _client().get("/api/admin/overview").status_code == 401


def test_wrong_key_returns_401():
    res = _client().get("/api/admin/overview", headers={"X-Admin-Key": "wrong"})
    assert res.status_code == 401


def test_unconfigured_key_returns_503():
    res = _client(admin_api_key="").get("/api/admin/overview", headers=_auth())
    assert res.status_code == 503


def test_overview_shape():
    traces = FakeTraceStore()
    traces.seed_turn("U1", "user", "hi", TODAY_TS)
    res = _client(traces).get("/api/admin/overview", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert body["turn_count"] == 1
    assert body["active_elder_count"] == 1
    assert {s["stage"] for s in body["stages"]} == {"asr", "llm", "tts"}
    assert isinstance(body["hourly_turns"], list)
    assert isinstance(body["generated_at"], float)


def test_list_elders():
    traces = FakeTraceStore()
    traces.seed_elder("e1", "阿公", "U1")
    traces.seed_turn("U1", "user", "hi", TODAY_TS)
    res = _client(traces).get("/api/admin/elders", headers=_auth())
    assert res.status_code == 200
    assert res.json()["elders"] == [
        {
            "elder_id": "e1",
            "name": "阿公",
            "line_user_id": "U1",
            "last_active_at": TODAY_TS,
        }
    ]
