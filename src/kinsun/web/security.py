"""基本安全標頭 middleware（✅ D-57，丙-9）。

全站統一掛：HSTS（對外恆經 ngrok HTTPS）、nosniff、預設禁 iframe、
不外洩 Referrer；CSP 以 self 為主，放寬四處——style 內聯（React 的
style 屬性）、media https:（admin 回放 Supabase 簽章音檔）、media blob:
與 script wasm（網頁版前端的語音播放與 QR 掃碼，2026-07-30）。
admin 金鑰存 localStorage 的既有風險由 CSP 補防（D-57 決議）。

唯一例外是網頁版阿白的離線 renderer：`/demo/otto/renderer.html` 只允許被
同源頁面嵌入。其 iframe 仍以 `sandbox="allow-scripts"` 隔離，不取得同源權限。
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

_DEMO_RENDERER_PATH = "/demo/otto/renderer.html"
_DEMO_RENDERER_CSP = (
    "default-src 'none'; "
    "img-src data:; "
    "style-src 'unsafe-inline'; "
    # renderer 是產生後的單一離線 HTML，白名單腳本都內嵌在檔案裡。不可沿用
    # 全站的 script-src 'self'：HTTP header 與 HTML meta CSP 會取交集，結果是
    # 內嵌腳本全被瀏覽器擋掉、iframe 永遠停在 opacity-0。
    "script-src 'unsafe-inline'; "
    "frame-ancestors 'self'"
)
_DEMO_RENDERER_HEADERS = {
    **SECURITY_HEADERS,
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": _DEMO_RENDERER_CSP,
}


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _add_security_headers(request, call_next):
        response = await call_next(request)
        # 阿白 renderer 是全站唯一需要被嵌入的文件。精確比對檔案路徑，避免把
        # `/demo/`、API 或其他靜態資產一起放寬成可被 iframe 包住。
        headers = (
            _DEMO_RENDERER_HEADERS
            if request.url.path == _DEMO_RENDERER_PATH
            else SECURITY_HEADERS
        )
        for name, value in headers.items():
            response.headers.setdefault(name, value)
        return response
