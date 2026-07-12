"""基本安全標頭 middleware（✅ D-57，丙-9）。

全站統一掛：HSTS（對外恆經 ngrok HTTPS）、nosniff、禁 iframe、
不外洩 Referrer；CSP 以 self 為主，放寬兩處——style 內聯（React 的
style 屬性）與 media https:（admin 回放 Supabase 簽章音檔）。
admin 金鑰存 localStorage 的既有風險由 CSP 補防（D-57 決議）。
"""

from __future__ import annotations

from fastapi import FastAPI

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "media-src 'self' https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": _CSP,
}


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _add_security_headers(request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
