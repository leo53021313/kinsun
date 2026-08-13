"""統一回應信封（✅ D-23 乙-1＋D-24 乙-2）：{success, data, error, meta}。

- 成功：handler 明確回 `ok(data, meta)`——顯式優於魔法，好 grep 好追。
- 失敗：`install_error_envelope(app)` 把 HTTPException 與 pydantic 驗證錯誤
  統一轉信封；error.code＝標準錯誤碼（06 §3）、error.message＝繁中人話
  （UI 直接顯示，未列表的碼以 code 原樣回）。
- 豁免（06 §2.4）：204 無 body、DGX healthz／TTS binary 不經本模組；
  LINE webhook 的錯誤會被全域 handler 轉信封——LINE 平台只看狀態碼，無影響。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# 標準錯誤碼 → 繁中人話（✅ D-24，06 §3）；UI 直接顯示 error.message。
ERROR_MESSAGES: dict[str, str] = {
    "missing_token": "請先登入",
    "invalid_token": "登入過期了，請重新登入",
    "not_found": "找不到這個頁面",
    "method_not_allowed": "現在不能做這件事",
    "invalid_schedule": "提醒的設定不正確",
    "invalid_credentials": "帳號或密碼不正確",
    "invalid_admin_key": "管理金鑰錯誤",
    "consent_revoked": "長輩的使用同意已失效",
    "elder_not_found": "找不到這位長輩",
    "medication_not_found": "找不到這筆用藥",
    "appointment_not_found": "找不到這筆回診",
    "trace_not_found": "找不到這筆鏈路紀錄",
    "strategy_not_found": "找不到這條守則，或它已經不在生效中",
    "invite_not_found": "查無此邀請碼",
    "email_taken": "這個 email 已經註冊過了",
    "phone_taken": "這個手機號碼已經幫另一位長輩註冊過了",
    "password_too_short": "密碼至少需要 8 個字元",
    "invalid_phone": "手機號碼格式不正確",
    "not_paired": "這支手機還沒完成配對，請先請家人提供綁定圖（QR）掃描一次",
    "invite_used": "邀請碼已被使用",
    "invite_expired": "邀請碼已過期",
    "invite_wrong_role": "這是家屬邀請碼，請改用長輩綁定碼",
    "too_many_attempts": "試太多次了，等一下再試",
    "too_many_requests": "按太快了，等一下再試",
    "name_required": "請輸入名稱",
    "label_required": "請輸入回診名稱",
    "slots_required": "請至少選擇一個提醒時段",
    "invalid_slot": "提醒時段格式不正確",
    "invalid_kind": "提醒類型不正確",
    "invalid_persona": "金孫的個性選項不正確",
    "kind_not_changeable": "提醒的類型不能修改，請刪掉這筆重新建立",
    "occurrences_required": "請至少設定一個提醒時間",
    "schedule_not_found": "找不到這筆提醒",
    "invalid_date": "日期格式不正確（YYYY-MM-DD）",
    "invalid_time": "時間格式不正確（HH:MM）",
    "date_in_past": "日期不可早於今天",
    "invalid_status": "現在的狀態沒辦法做這件事",
    "invalid_action": "現在不能做這件事",
    "validation_error": "有欄位沒填好，請檢查一下",
    "audio_too_large": "音檔太大，請縮短錄音再試一次",
    "missing_audio": "沒有收到錄音，請重新錄一次",
    "unsupported_media_type": "上傳格式不正確，請使用語音錄音",
    "consent_required": "請先確認這個聲音的主人同意提供",
    "speech_unavailable": "語音服務暫時無法使用，請稍後再試",
    "job_not_found": "找不到這個排程任務",
    "job_not_runnable_here": "這個排程由其他程序執行，後台無法在此立即觸發",
    "internal_testing_disabled": "內部測試模式未開啟",
    "admin_disabled": "服務未開放",
}


def ok(data, meta: dict | None = None) -> dict:
    return {"success": True, "data": data, "error": None, "meta": meta}


def error_body(code: str, message: str | None = None, meta: dict | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message or ERROR_MESSAGES.get(code, code)},
        "meta": meta,
    }


# 框架自己丟的 HTTPException（打錯網址、方法不對）帶的是英文句子（"Not Found"），
# 而 `detail` 會原封當成 `error.code`——那是**給機器判斷用的欄位**，塞英文句子等於
# 前端無從分支；`message` 又因為查無文案退回碼本身，於是使用者也看到英文。
# 專案規則是「`error.code` 唯一出處為 ErrorCode、每碼必有繁中文案」，框架丟的錯
# 不該是例外，故依狀態碼補上對應（A-04，2026-07-29）。
_FRAMEWORK_CODES: dict[int, str] = {
    404: "not_found",
    405: "method_not_allowed",
}


def _code_and_message(exc: StarletteHTTPException) -> tuple[str, str | None]:
    """從 HTTPException 取出 (code, message)。

    三種來源，優先序由具體到籠統：
    1. `detail` 是 `{"code": ..., "message": ...}`——業務驗證要同時給機器碼與**已經
       寫好的繁中人話**（A-01）。排程的驗證訊息（「那個時間已經過去了。」）是寫給長輩
       看的，LINE 流程與 LLM 工具都直接用它；HTTP 這條路原本把整句塞進 `error.code`。
    2. `detail` 是我們自己註冊過的碼——絕大多數情形，原樣放行。
    3. 其餘＝框架丟的英文句子，依狀態碼換成註冊過的碼。
    """
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return str(detail["code"]), detail.get("message")
    text = str(detail)
    if text in ERROR_MESSAGES:
        return text, None
    return _FRAMEWORK_CODES.get(exc.status_code, text), None


# pydantic 的錯誤型別 → 繁中人話（A-05，2026-07-29）。
#
# ⚠️ **絕不回傳 pydantic 自己的 `msg`**：它是英文散文，而且會把驗證用的正規表示式
# 原樣吐出去（實測 `"String should match pattern '^[^@]+@[^@]+\\.[^@]+$'"`）。那串
# pattern 是實作細節，對任何呼叫端都沒有用，卻等於把驗證規則公開；英文散文也既不能
# 直接顯示給家屬看、又不能拿來做程式分支。
#
# pydantic 另外給了機器可讀的 `type`，那才是該吐出去的：`code` 給機器分支，
# `message` 給人看。沒對應到的型別退回**泛用繁中**而不是英文原文——退回原文等於這道
# 防線在最需要的時候（遇到沒見過的錯）自動失效。
_FIELD_MESSAGES: dict[str, str] = {
    "missing": "這個欄位要填",
    "string_too_short": "字數不夠",
    "string_too_long": "字數太多",
    "string_pattern_mismatch": "格式不對",
    "string_type": "請填文字",
    "int_parsing": "請填整數",
    "int_type": "請填整數",
    "float_parsing": "請填數字",
    "float_type": "請填數字",
    "bool_parsing": "請選是或否",
    "bool_type": "請選是或否",
    "greater_than": "數字太小了",
    "greater_than_equal": "數字太小了",
    "less_than": "數字太大了",
    "less_than_equal": "數字太大了",
    "json_invalid": "資料格式不是有效的 JSON",
    "value_error": "這裡填的內容不對",
}
_FIELD_MESSAGE_FALLBACK = "這一欄填得不對"


def _field_message(error_type: str) -> str:
    return _FIELD_MESSAGES.get(error_type, _FIELD_MESSAGE_FALLBACK)


def install_error_envelope(app: FastAPI) -> None:
    """把 HTTPException／驗證錯誤統一改寫為信封格式（app 與測試的組裝處都要呼叫）。"""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_to_envelope(request, exc: StarletteHTTPException):
        code, message = _code_and_message(exc)
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))

    @app.exception_handler(RequestValidationError)
    async def _validation_to_envelope(request, exc: RequestValidationError):
        fields = [
            {
                "field": ".".join(str(part) for part in err.get("loc", [])),
                "code": str(err.get("type", "")),
                "message": _field_message(str(err.get("type", ""))),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", meta={"fields": fields}),
        )
