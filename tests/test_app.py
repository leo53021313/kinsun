"""web 組裝根：build_app 的整體接線煙霧測試（M-8 覆蓋補強）。

外部相依以假 Externals 替換，其餘接線（pipeline／閘門／routers／信封／
安全標頭）照常執行——驗證「app 建得起來、該掛的端點有掛」。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import kinsun.app as app_module
from kinsun.composition import Externals

_REQUIRED_ENV = {
    "LINE_CHANNEL_SECRET": "test-secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
    "GEMINI_API_KEY": "test-key",
    "DATABASE_URL": "postgresql://unused/unused",
    "ADMIN_API_KEY": "test-admin-key",
    # 固定為離線可組裝的形態：不建音檔託管、不掛 rich menu。
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_KEY": "",
    "TTS_BACKEND": "bubble",
    "RICH_MENU_ID": "",
}


class _FakeDb:
    def close(self) -> None:
        pass


class _FakeLLM:
    def generate(self, *, system_prompt, messages):
        return "好"

    def generate_tool_turn(self, **kwargs):
        raise NotImplementedError


def _build_app(monkeypatch):
    # ⚠️ 擋掉 build_app 內的 load_dotenv（2026-07-27）：它會把正式 .env 的 106 個鍵灌回
    # **整個測試行程**，而且汙染後面所有測試——conftest 的密封在這一行前功盡棄。
    # 這正是 ASR_BACKEND 洩漏的機制：`_REQUIRED_ENV` 覆寫了 TTS_BACKEND 卻沒覆寫
    # ASR_BACKEND，於是 .env 的 `dgx` 生效，單元測試真的建出指向正式 DGX 的
    # DgxAsrClient。守門的是 test_conftest_hermetic.py 與 conftest 的 pytest_sessionfinish。
    monkeypatch.setattr(app_module, "load_dotenv", lambda: None)
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        app_module,
        "build_externals",
        lambda settings: Externals(
            db=_FakeDb(), gemini=_FakeLLM(), long_term=object(), messenger=object()
        ),
    )
    return app_module.build_app()


def test_build_app_serves_healthz(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_build_app_mounts_v1_routers(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        paths = set(client.get("/openapi.json").json()["paths"])
    assert "/api/v1/turns" in paths  # App 對講機
    assert "/api/v1/admin/overview" in paths  # 觀測後台
    assert any(path.startswith("/api/v1/") and "elders" in path for path in paths)  # 家屬面


def test_build_app_wires_show_transcript_to_every_voice_delivery(monkeypatch):
    """ASR_DEBUG_SHOW_TRANSCRIPT 必須同時作用於 LINE 與 App 兩通道：App 對講機的
    VoiceReplyDelivery 是獨立實例，漏傳旗標會讓 debug 模式只有 LINE 看得到辨識文字、
    App 只剩回覆文字（2026-07-19 實錄）。"""
    captured: list[bool] = []

    class _SpyDelivery(app_module.VoiceReplyDelivery):
        def __init__(self, *args, **kwargs):
            captured.append(bool(kwargs.get("show_transcript", False)))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(app_module, "VoiceReplyDelivery", _SpyDelivery)
    monkeypatch.setenv("ASR_DEBUG_SHOW_TRANSCRIPT", "1")
    _build_app(monkeypatch)
    assert captured, "build_app 應至少建構一個 VoiceReplyDelivery"
    assert all(captured), f"有 VoiceReplyDelivery 漏傳 show_transcript：{captured}"


def test_build_app_installs_security_headers_and_envelope(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        res = client.get("/api/v1/admin/overview")  # 未帶金鑰 → 401 統一信封
    assert res.status_code == 401
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"]
    assert "content-security-policy" in res.headers


def test_網頁版前端在_dist_存在時掛在_demo(tmp_path, monkeypatch):
    """比照既有的 /liff 與 /admin：dist 不存在就不掛，不讓部署因為沒 build 而起不來。"""
    from kinsun.app import _static_mounts

    root = tmp_path
    (root / "web" / "dist").mkdir(parents=True)
    (root / "web" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    mounts = dict(_static_mounts(root))
    assert "/demo" in mounts
    assert mounts["/demo"] == root / "web" / "dist"


def test_網頁版前端未_build_時不掛載():
    from pathlib import Path

    from kinsun.app import _static_mounts

    mounts = dict(_static_mounts(Path("/nonexistent-root")))
    assert mounts == {}


def _spa_client(root):
    """把假的 web/dist 掛上去，走的是 build_app 用的同一段接線。"""
    from fastapi import FastAPI

    dist = root / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>金孫</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()
    app_module._mount_static(app, root)
    return TestClient(app)


def test_前端路由的網址由靜態檔回退到_index_html(tmp_path):
    """`/demo/stage` 是 spec §5.4 與 docs/dev/17 列在路由表上的網址，而且
    `navigate(..., {replace: true})` 會讓網址真的變成它——進到舞台後按重整、
    或把網址複製給別人，都會直接向伺服器要這條路徑。單頁應用沒有回退的話，
    使用者拿到的是 404，而他做的事情看起來完全正常。
    """
    client = _spa_client(tmp_path)
    assert client.get("/demo/").status_code == 200
    res = client.get("/demo/stage")
    assert res.status_code == 200
    assert "金孫" in res.text


def test_回退不吞掉資產的_404(tmp_path):
    """⚠️ 全部回退的話，一個打錯的資產路徑會拿到 200 ＋ 一頁 HTML，瀏覽器
    會安靜地渲染失敗——那比 404 難查得多。只有「最後一段沒有副檔名」的路徑
    才回退。
    """
    client = _spa_client(tmp_path)
    assert client.get("/demo/assets/app.js").status_code == 200
    assert client.get("/demo/assets/does-not-exist.js").status_code == 404
