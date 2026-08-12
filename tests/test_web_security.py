"""安全標頭與 CSP（✅ D-57 丙-9，2026-07-30 為網頁版前端放寬兩處）。

⚠️ 這兩處放寬各自對應一個**實測過**的失效：不加 blob: 則 WebSocket 直送的
回覆語音播不出來；不加 wasm-unsafe-eval 則 QR 掃碼的 WebAssembly 編譯被自家
CSP 擋死。兩者的症狀都是「靜默失效」——功能就是不動，主控台一行紅字。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.app import _SpaStaticFiles
from kinsun.web.security import SECURITY_HEADERS, install_security_headers


def _client():
    app = FastAPI()
    install_security_headers(app)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/demo/otto/renderer.html")
    def renderer() -> str:
        return "renderer"

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


def test_只有阿白_renderer_可被同源_demo_嵌入():
    client = _client()

    renderer_headers = client.get("/demo/otto/renderer.html").headers
    assert renderer_headers["x-frame-options"] == "SAMEORIGIN"
    renderer_csp = renderer_headers["content-security-policy"]
    assert "default-src 'none'" in renderer_csp
    assert "script-src 'unsafe-inline'" in renderer_csp
    assert "style-src 'unsafe-inline'" in renderer_csp
    assert "img-src data:" in renderer_csp
    assert "frame-ancestors 'self'" in renderer_csp
    assert "frame-ancestors 'none'" not in renderer_csp
    assert "connect-src 'self'" not in renderer_csp

    # 一般頁面仍維持 D-57 的全站預設；例外不可擴散到相鄰路徑。
    ordinary_headers = client.get("/ping").headers
    assert ordinary_headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in ordinary_headers["content-security-policy"]


def _demo_client(tmp_path):
    """掛**真的** `_SpaStaticFiles`，形狀與 `app.py` 的 `/demo` 一致。

    ⚠️ 上面那組測試用的是自己註冊的 `@app.get("/demo/otto/renderer.html")` 路由，
    它永遠只在「路徑逐字相符」時才會被叫到——也就是說**它結構上不可能發現
    「判斷用的路徑」與「決定回什麼內容的路徑」不一致**這種缺陷。而正式環境的
    `/demo` 是靜態檔掛載＋單頁應用回退，兩者行為差很多：`_SpaStaticFiles` 對
    找不到、且最後一段沒有副檔名的路徑，會回**應用殼 index.html**。
    """
    root = tmp_path / "demo"
    (root / "otto").mkdir(parents=True)
    (root / "index.html").write_text("<html>SPA 應用殼</html>", encoding="utf-8")
    (root / "otto" / "renderer.html").write_text("<html>renderer</html>", encoding="utf-8")

    app = FastAPI()
    install_security_headers(app)
    app.mount("/demo", _SpaStaticFiles(directory=root, html=True), name="demo")
    return TestClient(app)


@pytest.mark.parametrize(
    ("raw_path", "說明"),
    [
        ("/demo/otto/renderer.html%23a/b", "%23 解碼後是 #"),
        ("/demo/otto/renderer.html%3Fa/b", "%3F 解碼後是 ?"),
    ],
)
def test_放寬的標頭不會漏給單頁應用殼(tmp_path, raw_path, 說明):
    """判斷用的路徑必須與決定回應內容的路徑是**同一個**。

    ⚠️ 這是 2026-08-12 審查實測到的繞過（真 uvicorn 往返重現）：middleware 若用
    `request.url.path` 比對，Starlette 會把 scope 重組成完整網址再以 `urlsplit`
    切一次——`#` 之後被當成片段丟掉，於是 `/demo/otto/renderer.html%23a/b` 的
    `request.url.path` 是 `/demo/otto/renderer.html`（比對命中、掛上放寬的標頭），
    但路由實際看的 `scope["path"]` 是 `/demo/otto/renderer.html#a/b`（靜態檔找不到
    → 單頁應用回退 → **回 index.html**）。結果是應用殼帶著 `SAMEORIGIN`＋
    `frame-ancestors 'self'` 出去，而 PR 註解與 13 §2 都宣稱這不可能發生。

    `%3F` 是同一個機制的另一半（`?` 被當成 query 分隔）。
    """
    response = _demo_client(tmp_path).get(raw_path)

    # 先確認這條路徑真的回了應用殼——不然這條測試可能只是在測 404，形同虛設。
    assert response.status_code == 200
    assert "SPA 應用殼" in response.text, 說明

    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_真靜態掛載下_renderer_本人仍拿得到放寬的標頭(tmp_path):
    """修掉上面那條繞過之後，正牌 renderer 不可以連帶被擋掉。"""
    headers = _demo_client(tmp_path).get("/demo/otto/renderer.html").headers
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in headers["content-security-policy"]


def test_真靜態掛載下_相鄰的_demo_路徑仍被拒絕嵌入(tmp_path):
    """`/demo/stage` 是家屬與長輩實際在看的畫面，它必須維持全站的 DENY。"""
    headers = _demo_client(tmp_path).get("/demo/stage").headers
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
