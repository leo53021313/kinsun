"""信封底座單元測試（✅ 庚-43／A-58）：ok／error_body／install_error_envelope。

先前為唯一無專屬測試的底座件——信封是三端所有回應的形狀，改壞會全站
同時壞，值得最便宜的形狀鎖定。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kinsun.web.envelope import ERROR_MESSAGES, error_body, install_error_envelope, ok


def test_ok_shape():
    assert ok([1, 2]) == {"success": True, "data": [1, 2], "error": None, "meta": None}
    assert ok({}, meta={"limit": 5})["meta"] == {"limit": 5}


def test_error_body_uses_traditional_chinese_message_and_falls_back_to_code():
    body = error_body("invalid_date")
    assert body["error"] == {"code": "invalid_date", "message": ERROR_MESSAGES["invalid_date"]}
    unknown = error_body("no_such_code")
    assert unknown["error"]["message"] == "no_such_code"  # 查無文案退回碼本身


def _app() -> TestClient:
    app = FastAPI()
    install_error_envelope(app)

    class In(BaseModel):
        name: str

    @app.get("/boom")
    def boom() -> dict:
        raise HTTPException(status_code=404, detail="elder_not_found")

    @app.post("/validated")
    def validated(body: In) -> dict:
        return ok(body.name)

    return TestClient(app)


def test_http_exception_rewritten_to_envelope():
    res = _app().get("/boom")
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "elder_not_found"
    assert body["error"]["message"] == ERROR_MESSAGES["elder_not_found"]


def test_validation_error_rewritten_to_envelope():
    res = _app().post("/validated", json={})
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "validation_error"
    assert body["meta"] is not None and "fields" in body["meta"]
