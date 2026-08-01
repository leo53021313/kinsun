"""基本安全標頭 middleware（✅ D-57，丙-9）。

全站統一掛：HSTS（對外恆經 ngrok HTTPS）、nosniff、禁 iframe、
不外洩 Referrer；CSP 以 self 為主，放寬四處——style 內聯（React 的
style 屬性）、media https:（admin 回放 Supabase 簽章音檔）、media blob:
與 script wasm（網頁版前端的語音播放與 QR 掃碼，2026-07-30）。
admin 金鑰存 localStorage 的既有風險由 CSP 補防（D-57 決議）。
"""

from __future__ import annotations

from fastapi import FastAPI

_CSP = (
    "default-src 'self'; "
    # 'wasm-unsafe-eval'：長輩端掃 QR 用的 zxing-wasm 需要編譯 WebAssembly，而瀏覽器
    # 以 script-src 管制它（Chrome 起）。不加的症狀是掃碼完全沒反應、只有主控台一行
    # 紅字。刻意用 'wasm-unsafe-eval' 而非 'unsafe-eval'——後者連一般的 eval 都放行。
    "script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    # blob:：WebSocket 直送的回覆語音在網頁端只能落成 blob URL 再交給播放器
    # （expo-file-system 那條路在瀏覽器不存在）。不加就播不出聲音。
    "media-src 'self' https: blob:; "
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
