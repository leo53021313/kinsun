from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.routers import create_meta_router


def _client(*, internal_testing_enabled: bool) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_meta_router(internal_testing_enabled=internal_testing_enabled),
        prefix="/api/v1",
    )
    return TestClient(app)


def test_meta_is_public_and_reports_on():
    res = _client(internal_testing_enabled=True).get("/api/v1/meta")
    assert res.status_code == 200
    assert res.json()["data"] == {"internal_testing": True}


def test_meta_reports_off():
    res = _client(internal_testing_enabled=False).get("/api/v1/meta")
    assert res.json()["data"] == {"internal_testing": False}
