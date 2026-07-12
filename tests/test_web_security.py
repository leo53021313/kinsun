"""安全標頭 middleware（✅ D-57，丙-9）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.security import install_security_headers


def _client():
    app = FastAPI()
    install_security_headers(app)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_all_security_headers_present():
    res = _client().get("/ping")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in res.headers["Strict-Transport-Security"]
    csp = res.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    # admin 回放 Supabase 簽章音檔需 media https:（D-57 決議的刻意放寬）。
    assert "media-src 'self' https:" in csp
