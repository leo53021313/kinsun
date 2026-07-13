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
    "missing_token": "未提供登入憑證",
    "invalid_token": "登入憑證無效，請重新登入",
    "invalid_credentials": "帳號或密碼不正確",
    "invalid_admin_key": "管理金鑰錯誤",
    "consent_revoked": "長輩的使用同意已失效",
    "elder_not_found": "找不到這位長輩",
    "medication_not_found": "找不到這筆用藥",
    "appointment_not_found": "找不到這筆回診",
    "trace_not_found": "找不到這筆鏈路紀錄",
    "invite_not_found": "查無此邀請碼",
    "email_taken": "這個 email 已經註冊過了",
    "phone_taken": "這個手機號碼已經幫另一位長輩註冊過了",
    "password_too_short": "密碼至少需要 8 個字元",
    "invalid_phone": "手機號碼格式不正確",
    "not_paired": "這支手機還沒完成配對，請先請家人提供綁定圖（QR）掃描一次",
    "invite_used": "邀請碼已被使用",
    "invite_expired": "邀請碼已過期",
    "invite_wrong_role": "這是家屬邀請碼，請改用長輩綁定碼",
    "too_many_attempts": "嘗試次數過多，請稍後再試",
    "too_many_requests": "操作太頻繁，請稍後再試",
    "name_required": "請輸入名稱",
    "label_required": "請輸入回診名稱",
    "slots_required": "請至少選擇一個提醒時段",
    "invalid_slot": "提醒時段格式不正確",
    "invalid_date": "日期格式不正確（YYYY-MM-DD）",
    "invalid_time": "時間格式不正確（HH:MM）",
    "date_in_past": "日期不可早於今天",
    "validation_error": "輸入資料格式不正確",
    "audio_too_large": "音檔太大，請縮短錄音再試一次",
    "unsupported_media_type": "上傳格式不正確，請使用語音錄音",
    "job_not_found": "找不到這個排程任務",
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


def install_error_envelope(app: FastAPI) -> None:
    """把 HTTPException／驗證錯誤統一改寫為信封格式（app 與測試的組裝處都要呼叫）。"""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_to_envelope(request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_body(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_to_envelope(request, exc: RequestValidationError):
        fields = [
            {
                "field": ".".join(str(part) for part in err.get("loc", [])),
                "message": str(err.get("msg", "")),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", meta={"fields": fields}),
        )
