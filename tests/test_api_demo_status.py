"""公開運營狀態端點（W-03）：彙總規則、快取、探針隔離。

⚠️ 這支端點**不需認證**且對外公開，所以測試的重點有二：分項狀態的彙總規則
必須正確（按鈕能不能按由它決定），以及回應**不可**洩漏版本、主機名或錯誤內容。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers.demo_status import create_demo_status_router, overall_of

ALL_OK = {"database": "ok", "asr": "ok", "tts": "ok", "llm": "ok", "scheduler": "ok"}


def _client(components: dict, *, now=None, cache_seconds: float = 5.0):
    """把固定的分項狀態灌進去。probes 是注入點，測試完全不碰網路與資料庫。"""
    ticks = iter(now or [0.0] * 20)
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes={name: (lambda v=value: v) for name, value in components.items()},
            clock=lambda: next(ticks),
            cache_seconds=cache_seconds,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def test_全部正常時整體狀態為可用():
    assert overall_of(ALL_OK) == "available"


def test_資料庫不通即為停機():
    assert overall_of({**ALL_OK, "database": "down"}) == "down"


def test_語音辨識不通即為停機_因為對講機是核心功能():
    assert overall_of({**ALL_OK, "asr": "down"}) == "down"


def test_語音合成不通只是部分受限_聽得懂但不會出聲():
    assert overall_of({**ALL_OK, "tts": "down"}) == "degraded"


def test_排程器不通只是部分受限_提醒不會響但對講機還能用():
    assert overall_of({**ALL_OK, "scheduler": "down"}) == "degraded"


def test_模型載入中為啟動中_而非停機():
    """埠開了但 healthz 還沒好——等幾秒就會好，不該顯示成停機讓人放棄。"""
    assert overall_of({**ALL_OK, "asr": "loading"}) == "starting"


def test_停機優先於啟動中():
    """一個載入中、一個真的掛了，要報最嚴重的那個。"""
    assert overall_of({**ALL_OK, "asr": "loading", "database": "down"}) == "down"


def test_對話模型狀態不明不影響整體可用():
    """近期沒有呼叫紀錄時 llm 是 unknown——那是「不知道」，不是「壞了」。"""
    assert overall_of({**ALL_OK, "llm": "unknown"}) == "available"


def test_端點回傳整體狀態與分項():
    res = _client(ALL_OK).get("/api/v1/demo-status")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["overall"] == "available"
    assert body["data"]["components"] == ALL_OK


def test_回應不含任何可用於攻擊的細節():
    """公開端點只回粗粒度狀態：不吐版本、主機名、埠號、例外訊息。"""
    text = _client({**ALL_OK, "asr": "down"}).get("/api/v1/demo-status").text
    for leak in ("localhost", "127.0.0.1", "8001", "Traceback", "httpx", "postgres"):
        assert leak not in text


def test_快取期間內不重複呼叫探針():
    """公開端點不可成為健康檢查的放大器——有人狂重整就會把 ASR 打爆。"""
    calls = []

    def counting_probe() -> str:
        calls.append(1)
        return "ok"

    ticks = iter([0.0, 1.0, 2.0, 100.0])
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes={"database": counting_probe},
            clock=lambda: next(ticks),
            cache_seconds=5.0,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app)
    client.get("/api/v1/demo-status")
    client.get("/api/v1/demo-status")
    assert len(calls) == 1, "五秒內的第二次請求應該吃快取"
    client.get("/api/v1/demo-status")
    assert len(calls) == 1
    client.get("/api/v1/demo-status")
    assert len(calls) == 2, "快取過期後應該重新探測"


def test_探針自己爆掉時該分項為不明_而不是整支端點掛掉():
    """探針是對外呼叫，它會失敗。失敗時這一頁必須還開得起來。"""

    def exploding_probe() -> str:
        raise RuntimeError("連不上")

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes={"database": lambda: "ok", "asr": exploding_probe},
            clock=lambda: 0.0,
            cache_seconds=5.0,
        ),
        prefix="/api/v1",
    )
    res = TestClient(app).get("/api/v1/demo-status")
    assert res.status_code == 200
    assert res.json()["data"]["components"]["asr"] == "unknown"
