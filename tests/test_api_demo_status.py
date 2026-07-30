"""公開運營狀態端點（W-03）：彙總規則、快取、探針隔離。

⚠️ 這支端點**不需認證**且對外公開，所以測試的重點有二：分項狀態的彙總規則
必須正確（按鈕能不能按由它決定），以及回應**不可**洩漏版本、主機名或錯誤內容。
"""

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers.demo_status import (
    COMPONENT_NAMES,
    create_demo_status_router,
    overall_of,
)

ALL_OK = {"database": "ok", "asr": "ok", "tts": "ok", "llm": "ok", "scheduler": "ok"}


def _all_ok_probes(**overrides):
    """完整的一組探針。

    ⚠️ 每個分項都要有：`create_demo_status_router` 會擋下缺項——`_CRITICAL` 靠
    `components.get(name)` 判斷，鍵不存在時是 None、`None != "down"`，於是
    「ASR 掛掉＝整體停機」會悄悄失效。
    """
    probes = {name: (lambda: "ok") for name in COMPONENT_NAMES}
    probes.update(overrides)
    return probes


def _handler_of(**kwargs):
    """取出路由背後的函式，直接從多條執行緒呼叫——快取的鎖是 threading.Lock，
    這樣測到的就是它本身，不必繞過 ASGI 與執行緒池。"""
    router = create_demo_status_router(**kwargs)
    return router.routes[0].endpoint


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
            probes=_all_ok_probes(database=counting_probe),
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


def test_關鍵項探針爆掉時該分項為停機_且整體亦為停機():
    """探針是對外呼叫，連線失敗時很常見地會直接拋例外、而不是自己接住改回傳
    down（例如 OperationalError、httpx.ConnectError 沒被接住）。資料庫與語音
    辨識是這一頁存在的理由，問不出來就必須當成停機——若誤判成 unknown、
    overall 卻不受影響，按鈕會保持可按，讓人以為對講機能用，一開口才發現
    根本連不上。
    """

    def exploding_probe() -> str:
        raise RuntimeError("連不上")

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes=_all_ok_probes(asr=exploding_probe),
            clock=lambda: 0.0,
            cache_seconds=5.0,
        ),
        prefix="/api/v1",
    )
    res = TestClient(app).get("/api/v1/demo-status")
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["components"]["asr"] == "down"
    assert body["data"]["overall"] == "down"


def test_非關鍵項探針爆掉時該分項為不明_整體仍為可用():
    """語音合成不是這一頁的關鍵項——問不出來只代表「不知道」，不該連帶把
    整體判定成停機，否則會在非核心服務短暫抖動時錯誤地擋掉使用者。"""

    def exploding_probe() -> str:
        raise RuntimeError("連不上")

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes=_all_ok_probes(tts=exploding_probe),
            clock=lambda: 0.0,
            cache_seconds=5.0,
        ),
        prefix="/api/v1",
    )
    res = TestClient(app).get("/api/v1/demo-status")
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["components"]["tts"] == "unknown"
    assert body["data"]["overall"] == "available"


def test_探針爆掉不會讓端點本身掛掉():
    """不論爆掉的是關鍵項還是非關鍵項，端點都必須還開得起來——這一頁存在的
    目的就是在系統出問題時仍然能顯示狀態，不能自己先掛點。"""

    def exploding_probe() -> str:
        raise RuntimeError("連不上")

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_demo_status_router(
            probes={name: exploding_probe for name in COMPONENT_NAMES},
            clock=lambda: 0.0,
            cache_seconds=5.0,
        ),
        prefix="/api/v1",
    )
    res = TestClient(app).get("/api/v1/demo-status")
    assert res.status_code == 200


def test_探針缺少分項時在建立路由就擲出():
    """⚠️ `_CRITICAL` 用 `components.get(name) == DOWN` 判斷，鍵不存在時是 None、
    `None != "down"`，於是「ASR 掛掉＝整體停機」這條規則會**悄悄**失效：畫面顯示
    available、按鈕可按，而語音辨識根本沒被問過。組裝時漏接一支探針不該要等到
    有人在展示現場開口說話才發現，所以在建立路由的那一刻就炸。
    """
    with pytest.raises(ValueError, match="asr"):
        create_demo_status_router(probes={"database": lambda: "ok"})


def test_探針齊全時正常建立():
    assert create_demo_status_router(probes=_all_ok_probes()) is not None


def test_併發請求只有一條執行緒真的去探測():
    """一次 cache miss 的成本是兩次 healthz（各 1.5 秒逾時）＋埠探測＋資料庫＋
    traces 統計＋每支排程 job 兩次查詢——ASR／TTS 真的掛掉時最慢約四秒。而這支
    端點公開、免認證、經 ngrok 對外，底下的 handler 全是同步 def、共用 anyio 那
    40 條執行緒池。沒有 single-flight 的話，快取一過期，所有併發請求會一起穿透
    去打同一台正在重啟的 GPU 服務。
    """
    probing = threading.Event()
    finish = threading.Event()
    calls: list[int] = []

    def slow_probe() -> str:
        calls.append(1)
        probing.set()
        finish.wait(timeout=5.0)
        return "ok"

    handler = _handler_of(
        probes=_all_ok_probes(asr=slow_probe), clock=lambda: 0.0, cache_seconds=5.0
    )
    results: list[dict] = []
    threads = [threading.Thread(target=lambda: results.append(handler())) for _ in range(2)]
    threads[0].start()
    assert probing.wait(timeout=5.0), "第一條執行緒應該已經開始探測"
    threads[1].start()
    time.sleep(0.05)  # 讓第二條執行緒真的走到快取那一段
    finish.set()
    for thread in threads:
        thread.join(timeout=5.0)

    assert len(calls) == 1, "併發的第二個請求不該觸發第二次探測"
    assert len(results) == 2
    assert all(result["data"]["components"]["asr"] == "ok" for result in results)


def test_快取過期時併發請求拿上一份舊資料_而不是排隊等新的():
    """公開端點寧可回舊資料，也不要三十條執行緒同時去打一台正在重啟的 GPU 服務。
    拿不到鎖的請求立刻回上一份快取（即使過期），不等。
    """
    now = [0.0]
    probing = threading.Event()
    finish = threading.Event()
    calls: list[int] = []

    def slow_probe() -> str:
        calls.append(1)
        probing.set()
        finish.wait(timeout=5.0)
        return "ok"

    handler = _handler_of(
        probes=_all_ok_probes(asr=slow_probe), clock=lambda: now[0], cache_seconds=5.0
    )
    finish.set()
    handler()  # 先把快取灌熱
    assert len(calls) == 1

    finish.clear()
    probing.clear()
    now[0] = 100.0  # 快取過期
    thread = threading.Thread(target=handler)
    thread.start()
    assert probing.wait(timeout=5.0), "背景那一條應該已經開始探測"

    started_at = time.monotonic()
    body = handler()
    elapsed = time.monotonic() - started_at

    assert len(calls) == 2, "第二個請求不該再探一次"
    assert body["data"]["components"]["asr"] == "ok", "應該拿到上一份快取"
    assert elapsed < 1.0, f"不該排隊等前一個探測做完（等了 {elapsed:.2f} 秒）"
    finish.set()
    thread.join(timeout=5.0)


def test_第一次請求沒有任何快取可回時要等_不可回空():
    """⚠️ 冷啟動時拿不到鎖不能回 None——那會讓前端拿到一個沒有 overall 的回應。
    這時必須等第一次探測做完。
    """
    handler = _handler_of(probes=_all_ok_probes(), clock=lambda: 0.0, cache_seconds=5.0)
    results: list[dict] = []
    threads = [threading.Thread(target=lambda: results.append(handler())) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
    assert len(results) == 4
    assert all(result["data"]["overall"] == "available" for result in results)


# --- 真實探針 ---

from datetime import UTC, datetime, timedelta  # noqa: E402

from kinsun.transport import FakeTransport, Response, TransportError  # noqa: E402
from kinsun.web.routers.demo_status import (  # noqa: E402
    database_probe,
    healthz_url_of,
    http_healthz_probe,
    llm_probe,
    scheduler_probe,
    service_probe,
)


def test_healthz_位址由服務位址推導():
    """ASR_ENDPOINT 指的是 /transcribe 那一支，healthz 在同一個主機的根路徑下。"""
    assert healthz_url_of("http://127.0.0.1:8001/transcribe") == "http://127.0.0.1:8001/healthz"
    assert healthz_url_of("http://127.0.0.1:8002/synthesize") == "http://127.0.0.1:8002/healthz"


def test_healthz_位址_對沒有路徑的位址也要算得對():
    """字串切割在這裡會算出 http://healthz 這種壞網址，所以用正規的 URL 解析。"""
    assert healthz_url_of("http://127.0.0.1:8001") == "http://127.0.0.1:8001/healthz"
    assert healthz_url_of("https://asr.example.com/") == "https://asr.example.com/healthz"


def test_healthz_位址_未設定時為空字串():
    assert healthz_url_of("") == ""


def test_healthz_探針_二百回應為正常():
    transport = FakeTransport([Response(200, {}, b'{"status":"ok"}')])
    assert http_healthz_probe("http://svc/healthz", transport=transport, timeout=1.5)() == "ok"


def test_healthz_探針_連不上為停機():
    transport = FakeTransport()
    transport.error = TransportError("connection refused")
    assert http_healthz_probe("http://svc/healthz", transport=transport, timeout=1.5)() == "down"


def test_healthz_探針_未設定位址時為不明():
    """ASR_ENDPOINT 沒設＝這個部署沒接語音服務，不是它壞了。"""
    transport = FakeTransport()
    assert http_healthz_probe("", transport=transport, timeout=1.5)() == "unknown"
    assert transport.calls == [], "沒有位址就不該發出任何請求"


def test_服務探針_healthz_通即為正常():
    transport = FakeTransport([Response(200, {}, b"{}")])
    probe = service_probe(
        "http://127.0.0.1:8001/transcribe",
        transport=transport,
        port_check=lambda host, port: True,
    )
    assert probe() == "ok"


def test_服務探針_healthz_不通但埠開著為載入中():
    """⚠️ 這一條是 starting 狀態唯一的來源。沒有它，overall_of 的 starting
    分支永遠不會發生，而「模型還在載入」會被顯示成「停機」——那是內部測試
    最常遇到的狀況，也是最容易讓人白等或白放棄的誤報。"""
    transport = FakeTransport()
    transport.error = TransportError("connection refused")
    probe = service_probe(
        "http://127.0.0.1:8001/transcribe",
        transport=transport,
        port_check=lambda host, port: True,
    )
    assert probe() == "loading"


def test_服務探針_埠也沒開為停機():
    transport = FakeTransport()
    transport.error = TransportError("connection refused")
    probe = service_probe(
        "http://127.0.0.1:8001/transcribe",
        transport=transport,
        port_check=lambda host, port: False,
    )
    assert probe() == "down"


def test_服務探針_未設定位址時為不明_且完全不碰網路():
    transport = FakeTransport()
    calls = []
    probe = service_probe(
        "",
        transport=transport,
        port_check=lambda host, port: calls.append((host, port)) or True,
    )
    assert probe() == "unknown"
    assert transport.calls == []
    assert calls == []


def test_服務探針_從位址解出主機與埠():
    transport = FakeTransport()
    transport.error = TransportError("nope")
    seen = []
    probe = service_probe(
        "http://10.0.0.5:8002/synthesize",
        transport=transport,
        port_check=lambda host, port: seen.append((host, port)) or False,
    )
    probe()
    assert seen == [("10.0.0.5", 8002)]


def test_資料庫探針_查得動為正常():
    class Db:
        def query_one(self, sql, params=()):
            return (1,)

    assert database_probe(Db())() == "ok"


def test_資料庫探針_查不動為停機():
    class Db:
        def query_one(self, sql, params=()):
            raise RuntimeError("connection pool exhausted")

    assert database_probe(Db())() == "down"


class _Stage:
    def __init__(self, stage, call_count, error_count):
        self.stage = stage
        self.call_count = call_count
        self.error_count = error_count


class _Traces:
    def __init__(self, stages):
        self._stages = stages
        self.windows = []

    def get_overview_stats(self, *, today_start, hourly_start):
        self.windows.append(today_start)
        return type("S", (), {"stages": self._stages})()


def test_對話模型探針_近期無呼叫為不明():
    """沒有人講話時談不上健康或不健康。回 unknown 而不是 ok——不知道就說不知道。"""
    assert llm_probe(_Traces([]), clock=lambda: 1000.0)() == "unknown"


def test_對話模型探針_近期全成功為正常():
    stages = [_Stage("llm:care", 10, 0), _Stage("asr", 10, 5)]
    assert llm_probe(_Traces(stages), clock=lambda: 1000.0)() == "ok"


def test_對話模型探針_近期過半失敗為停機():
    stages = [_Stage("llm:care", 10, 6)]
    assert llm_probe(_Traces(stages), clock=lambda: 1000.0)() == "down"


def test_對話模型探針_只看時間窗內的資料():
    traces = _Traces([_Stage("llm:care", 1, 0)])
    llm_probe(traces, clock=lambda: 1000.0, window_seconds=600.0)()
    assert traces.windows == [400.0], "應該只查最近十分鐘，不是查一整天"


class _Spec:
    def __init__(self, name, cron, max_lateness_seconds=None):
        self.name = name
        self.cron = cron
        self.max_lateness_seconds = max_lateness_seconds


class _State:
    def __init__(self, last_runs, last_successes=None):
        self._last_runs = last_runs
        self._last_successes = last_successes or {}

    def get_last_run(self, name):
        return self._last_runs.get(name)

    def get_last_success(self, name):
        return self._last_successes.get(name)


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def test_排程器探針_每分鐘的工作剛跑過為正常():
    state = _State({"schedule-dispatch": NOW - timedelta(seconds=30)})
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "ok"


def test_排程器探針_逾期為停機():
    """2026-07-26 排程器假死七小時、狀態列全程顯示 RUNNING——只看程序在不在會說謊。"""
    state = _State({"schedule-dispatch": NOW - timedelta(hours=7)})
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "down"


def test_排程器探針_從未執行過為不明():
    """剛部署完還沒跑過第一輪，不該一開機就報紅。"""
    state = _State({})
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "unknown"


def test_排程器探針_全部工作都從未執行過為不明():
    """兩支工作都還沒跑過第一輪——不該一開機就報紅。"""
    state = _State({})
    specs = [
        _Spec("schedule-dispatch", "* * * * *", 90),
        _Spec("nightly-batch", "0 3 * * *", 300),
    ]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "unknown"


def test_排程器探針_有支跑過但另一支從未執行過為停機():
    """排程器活著卻沒認領那支工作，是這裡看得到的情形裡最嚴重的一種，
    不能被別支正常運作的工作遮蔽掉。"""
    state = _State({"schedule-dispatch": NOW - timedelta(seconds=30)})
    specs = [
        _Spec("schedule-dispatch", "* * * * *", 90),
        _Spec("nightly-batch", "0 3 * * *", 300),
    ]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "down"


def test_排程器探針_一直在跑但一直失敗為停機():
    """last_run_at 由 _claim_if_due 在執行之前寫入（at-most-once 搶占所必需），
    每輪都失敗的工作照樣按時更新 last_run_at，只看逾期看不出來——要靠成功紀錄
    落後超過容許量才分得出來。"""
    state = _State(
        {"schedule-dispatch": NOW - timedelta(seconds=30)},
        {"schedule-dispatch": NOW - timedelta(hours=7)},
    )
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "down"


def test_排程器探針_沒有成功紀錄但準時執行為正常():
    """last_success 為 None 不等於失敗——可能是真的從沒成功過，也可能是這個
    欄位上線前的舊資料，兩者都不可當成失敗，否則第一次部署整排就會變紅。"""
    state = _State({"schedule-dispatch": NOW - timedelta(seconds=30)})
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "ok"


def test_排程器探針_全部準時且有成功紀錄為正常():
    state = _State(
        {"schedule-dispatch": NOW - timedelta(seconds=30)},
        {"schedule-dispatch": NOW - timedelta(seconds=30)},
    )
    specs = [_Spec("schedule-dispatch", "* * * * *", 90)]
    assert scheduler_probe(state, specs, clock=lambda: NOW)() == "ok"
