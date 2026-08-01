"""安全標頭與 CSP（✅ D-57 丙-9，2026-07-30 為網頁版前端放寬兩處）。

⚠️ 這兩處放寬各自對應一個**實測過**的失效：不加 blob: 則 WebSocket 直送的
回覆語音播不出來；不加 wasm-unsafe-eval 則 QR 掃碼的 WebAssembly 編譯被自家
CSP 擋死。兩者的症狀都是「靜默失效」——功能就是不動，主控台一行紅字。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.security import SECURITY_HEADERS, install_security_headers


def _client():
    app = FastAPI()
    install_security_headers(app)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    return TestClient(app)


def _csp() -> dict[str, str]:
    """把 CSP 字串拆成 {指令: 值}，斷言才不必依賴字串裡的空白與順序。"""
    parts = SECURITY_HEADERS["Content-Security-Policy"].split(";")
    directives = {}
    for part in parts:
        name, _, value = part.strip().partition(" ")
        directives[name] = value
    return directives


def test_媒體來源允許_blob_否則播不出_WebSocket_直送的語音():
    assert "blob:" in _csp()["media-src"]


def test_腳本來源允許_wasm_否則_QR_掃碼被自家_CSP_擋死():
    assert "'wasm-unsafe-eval'" in _csp()["script-src"]


def test_腳本來源仍不允許_unsafe_eval():
    """wasm-unsafe-eval 只放行 WebAssembly 編譯；一般的 eval 仍然要擋。"""
    assert "'unsafe-eval'" not in _csp()["script-src"]


def test_既有的四道防線沒有被順手放鬆():
    directives = _csp()
    assert directives["default-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["connect-src"] == "'self'"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"


def test_標頭真的會出現在回應上():
    headers = _client().get("/ping").headers
    for name, value in SECURITY_HEADERS.items():
        assert headers[name] == value
