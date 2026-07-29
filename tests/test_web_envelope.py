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


# ── 框架層錯誤也要走繁中信封（A-04，2026-07-29）────────────────────────


def _bare_app() -> TestClient:
    app = FastAPI()
    install_error_envelope(app)

    @app.get("/api/v1/things")
    def things() -> dict:
        return ok([])

    return TestClient(app)


def test_framework_404_gets_a_machine_readable_code_not_an_english_sentence():
    """打錯網址時，FastAPI 自己丟的 detail 是英文句子「Not Found」，而它會原封當成
    `error.code`——那是**給機器判斷用的欄位**，一個英文句子等於前端無從分支；
    `message` 又因為查無文案退回碼本身，於是連使用者也看到英文。

    專案規則寫得很明確：`error.code` 的唯一出處是 `ErrorCode`、每碼必有繁中文案。
    框架自己丟的錯不該是這條規則的例外。
    """
    res = _bare_app().get("/api/v1/no-such-path")
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == ERROR_MESSAGES["not_found"]


def test_framework_405_gets_a_machine_readable_code():
    res = _bare_app().post("/api/v1/things", json={})
    assert res.status_code == 405
    assert res.json()["error"]["code"] == "method_not_allowed"


def test_our_own_error_codes_are_untouched():
    """路由自己丟的 ErrorCode 不可被框架對應表蓋掉——那才是絕大多數的情形。"""
    app = FastAPI()
    install_error_envelope(app)

    @app.get("/api/v1/gone")
    def gone() -> dict:
        raise HTTPException(status_code=404, detail="elder_not_found")

    res = TestClient(app).get("/api/v1/gone")
    assert res.json()["error"]["code"] == "elder_not_found"


def test_detail_may_carry_both_a_code_and_a_human_message():
    """業務驗證要能同時給「機器判斷的碼」與「已經寫好的繁中人話」（A-01）。

    排程的驗證訊息（如「那個時間已經過去了。」）是寫給長輩看的，LINE 流程與 LLM
    工具都直接用它；但 HTTP 這條路原本把整句話塞進 `error.code`，前端沒辦法分支。
    """
    app = FastAPI()
    install_error_envelope(app)

    @app.get("/api/v1/boom")
    def boom() -> dict:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_schedule", "message": "那個時間已經過去了。"},
        )

    body = TestClient(app).get("/api/v1/boom").json()
    assert body["error"] == {"code": "invalid_schedule", "message": "那個時間已經過去了。"}
