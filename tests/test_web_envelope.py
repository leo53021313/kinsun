"""信封底座單元測試（✅ 庚-43／A-58）：ok／error_body／install_error_envelope。

先前為唯一無專屬測試的底座件——信封是三端所有回應的形狀，改壞會全站
同時壞，值得最便宜的形狀鎖定。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

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


# ── 422 欄位明細不得外洩實作細節（A-05，2026-07-29）──────────────────────


# ⚠️ 這兩個模型必須住在**模組層級**：本檔有 `from __future__ import annotations`，
# 型別註記會變成字串，FastAPI 只能從模組 globals 解析——定義在函式裡的類別它找不到，
# 於是把參數當成 query 而回 `missing`，測試會以看似無關的方式紅掉。
class _PatternIn(BaseModel):
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(min_length=8)


class _CountIn(BaseModel):
    count: int


def test_field_errors_carry_a_machine_code_and_chinese_message_not_pydantic_prose():
    """pydantic 的 `msg` 是英文散文，而且**會把正規表示式原樣吐出去**：
    實測 `"String should match pattern '^[^@]+@[^@]+\\.[^@]+$'"`。

    兩個問題疊在一起：
    - 那串 pattern 是**實作細節**，對任何呼叫端都沒有用，卻等於把驗證規則公開；
    - 英文散文既不能直接顯示給家屬看，也不能拿來做程式分支。

    pydantic 另外給了機器可讀的 `type`（`string_pattern_mismatch`／`string_too_short`
    …），那才是該吐出去的東西。故 `meta.fields` 改成 `{field, code, message}`：
    code 給機器、message 給人，兩者都不再是英文原文。
    """
    app = FastAPI()
    install_error_envelope(app)

    @app.post("/api/v1/x")
    def x(body: _PatternIn) -> dict:
        return ok({})

    body = TestClient(app).post("/api/v1/x", json={"email": "bad", "password": "s"}).json()
    fields = {f["field"]: f for f in body["meta"]["fields"]}
    assert fields["body.email"]["code"] == "string_pattern_mismatch"
    assert fields["body.password"]["code"] == "string_too_short"
    # 關鍵斷言：pattern 絕不可出現在回應裡的任何一處。
    raw = str(body)
    assert "^[^@]" not in raw
    assert "String should" not in raw
    # 訊息是繁中人話。
    assert all(f["message"] and not f["message"].isascii() for f in fields.values())


def test_unmapped_field_error_falls_back_to_generic_chinese_not_english():
    """沒對應到的 pydantic 型別退回**泛用繁中**，而不是退回英文原文——
    退回原文等於這道防線在最需要的時候（遇到沒見過的錯）自動失效。"""
    app = FastAPI()
    install_error_envelope(app)

    @app.post("/api/v1/y")
    def y(body: _CountIn) -> dict:
        return ok({})

    body = TestClient(app).post("/api/v1/y", json={"count": "不是數字"}).json()
    field = body["meta"]["fields"][0]
    assert field["code"] == "int_parsing"
    assert not field["message"].isascii()
