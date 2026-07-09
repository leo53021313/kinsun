"""統一回應信封（✅ D-23，乙-1）：{success, data, error, meta}。

- 成功：handler 明確回 `ok(data, meta)`——顯式優於魔法，好 grep 好追。
- 失敗：`install_error_envelope(app)` 把 HTTPException 統一轉信封；
  error.code 目前沿用各 handler 的 detail 字串，標準碼與中文 message
  於乙-2（D-24）統一。
- 豁免（06 §2.4）：204 無 body、LINE webhook、DGX healthz／TTS binary——
  皆不經本模組。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def ok(data, meta: dict | None = None) -> dict:
    return {"success": True, "data": data, "error": None, "meta": meta}


def error_body(code: str, message: str | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message or code},
        "meta": None,
    }


def install_error_envelope(app: FastAPI) -> None:
    """把 HTTPException 統一改寫為信封格式（app 與測試的組裝處都要呼叫）。"""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_to_envelope(request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code, content=error_body(str(exc.detail))
        )
