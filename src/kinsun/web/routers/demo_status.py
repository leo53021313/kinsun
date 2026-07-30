"""公開運營狀態端點（spec 2026-07-30 W-03）：`GET /api/v1/demo-status`。

網頁版前端一進站就打這一支，據此決定「開始使用」按鈕能不能按。

⚠️ **公開、不需認證**，所以只回粗粒度狀態：分項一律是四個字面值之一，
不含版本、主機名、埠號或例外訊息——那些對前端沒有用，對掃描的人很有用。

⚠️ **結果快取**：有人壓著重整就會把 ASR 與 TTS 的 healthz 打爆，那正是這一頁
要偵測的服務。快取讓探測頻率與請求頻率脫鉤。
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from croniter import croniter
from fastapi import APIRouter

from kinsun.transport import HttpxTransport, Transport, TransportError
from kinsun.web.envelope import ok

logger = logging.getLogger("kinsun.web.demo_status")

# 分項狀態。`unknown` 是「問不出來」（探針爆了、近期無資料），刻意與 `down` 分開
# ——把不知道當成壞掉，會讓這一頁在最需要它的時候變成狼來了。
OK = "ok"
LOADING = "loading"
DOWN = "down"
UNKNOWN = "unknown"

# 整體狀態。前端據此決定按鈕：available／degraded 可按，starting／down 不可按。
AVAILABLE = "available"
DEGRADED = "degraded"
STARTING = "starting"
DOWN_OVERALL = "down"

# 這兩項掛掉＝產品的核心功能不存在，讓人進去只會得到壞掉的印象。
# ASR 在列是因為對講機是本產品唯一的核心互動；TTS 不在列——聽得懂但不會出聲
# 仍然看得到字幕，是可用的降級。
_CRITICAL = ("database", "asr")

# 分項的完整清單與順序（前端照這個順序顯示燈號）。
COMPONENT_NAMES = ("database", "asr", "tts", "llm", "scheduler")


def overall_of(components: Mapping[str, str]) -> str:
    """由分項狀態算出整體狀態。純函式，優先序：停機 > 啟動中 > 部分受限 > 可用。"""
    if any(components.get(name) == DOWN for name in _CRITICAL):
        return DOWN_OVERALL
    if any(status == LOADING for status in components.values()):
        return STARTING
    if any(status == DOWN for status in components.values()):
        return DEGRADED
    return AVAILABLE


def create_demo_status_router(
    *,
    probes: Mapping[str, Callable[[], str]],
    clock: Callable[[], float] = time.monotonic,
    cache_seconds: float = 5.0,
) -> APIRouter:
    """probes 是注入點：鍵＝分項名稱，值＝回傳分項狀態的函式（不得拋出，但這裡仍接住）。"""
    router = APIRouter(tags=["demo"])
    cache: dict[str, object] = {"at": None, "payload": None}

    def probe_all() -> dict[str, str]:
        result: dict[str, str] = {}
        for name, probe in probes.items():
            try:
                result[name] = probe()
            except Exception:  # noqa: BLE001 - 探針是對外呼叫，它一定會失敗；不可讓它帶走整頁
                logger.warning("運營狀態探針失敗：%s", name)
                # 關鍵項（database／asr）連例外都拋出來，代表真的連不上（例如
                # OperationalError、httpx.ConnectError 沒被探針自己接住），不是
                # 「這個部署沒接這個服務」——那種情形探針會明確回傳 unknown，不會
                # 拋例外，此處完全不動那條路。關鍵項在此一律當成停機：寧可錯殺、
                # 不可放過，誤擋的代價是使用者多等幾秒重查，誤放的代價是讓人以為
                # 對講機能用、一開口才發現連不上。非關鍵項則維持 unknown。
                result[name] = DOWN if name in _CRITICAL else UNKNOWN
        return result

    @router.get("/demo-status")
    def demo_status() -> dict:
        now = clock()
        last_at = cache["at"]
        if last_at is not None and now - float(last_at) < cache_seconds:
            return ok(cache["payload"])
        components = probe_all()
        payload = {"overall": overall_of(components), "components": components}
        cache["at"] = now
        cache["payload"] = payload
        return ok(payload)

    return router


# --- 真實探針 ---
#
# 每個探針都是「無參數、回傳分項狀態字串」的閉包，這樣路由完全不必知道分項是怎麼
# 問出來的，測試也就不必碰網路與資料庫。


def healthz_url_of(endpoint: str) -> str:
    """把服務的 endpoint（如 `.../transcribe`）換成同一台主機的 `/healthz`。

    ⚠️ 用 `urlsplit` 而不是字串切割：位址若沒有路徑（`http://host:8001`），
    切最後一段會算出 `http://healthz` 這種連得上但完全不對的網址，而症狀是
    「這個服務永遠顯示停機」——查起來會非常久。
    """
    if not endpoint:
        return ""
    parts = urlsplit(endpoint)
    return urlunsplit((parts.scheme, parts.netloc, "/healthz", "", ""))


def tcp_port_open(host: str, port: int, *, timeout: float = 0.5) -> bool:
    """埠有沒有人在聽。逾時要更短——這只是在 healthz 已經失敗之後補問一句。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_healthz_probe(
    url: str,
    *,
    transport: Transport | None = None,
    timeout: float = 1.5,
) -> Callable[[], str]:
    """打對方的 `/healthz`。位址空字串＝這個部署沒接這個服務，回 unknown 而非 down。

    ⚠️ 逾時要短（預設 1.5 秒）：這支端點是使用者進站看到的第一個畫面，
    不可以被一個連不上的服務拖住五秒。
    """
    client = transport or HttpxTransport()

    def probe() -> str:
        if not url:
            return UNKNOWN
        try:
            response = client.request("GET", url, timeout=timeout)
        except TransportError:
            return DOWN
        return OK if 200 <= response.status < 300 else DOWN

    return probe


def service_probe(
    endpoint: str,
    *,
    transport: Transport | None = None,
    timeout: float = 1.5,
    port_check: Callable[[str, int], bool] = lambda host, port: tcp_port_open(host, port),
) -> Callable[[], str]:
    """ASR／TTS 這種「有 healthz 的獨立服務」的完整探針。

    ⚠️ **healthz 不通但埠是開的＝模型還在載入**，這是本函式存在的唯一理由，
    也是 `overall_of` 的 `starting` 狀態唯一的來源。「載入中」與「沒開」在畫面上
    是兩件完全不同的事：前者再等十秒就好，後者要有人去下指令。分不出來的話，
    使用者只能盲等或盲放棄——而這是內部測試最常遇到的狀況。
    判斷與 `scripts/kinsun.sh` 的 `_health_note` 同源。
    """
    healthz = http_healthz_probe(healthz_url_of(endpoint), transport=transport, timeout=timeout)
    parts = urlsplit(endpoint) if endpoint else None

    def probe() -> str:
        status = healthz()
        if status in (OK, UNKNOWN):
            return status
        if parts is None or not parts.hostname:
            return DOWN
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return LOADING if port_check(parts.hostname, port) else DOWN

    return probe


def database_probe(db) -> Callable[[], str]:
    """最便宜的連通性驗證。查不動就是查不動，不細分原因——那是 log 的工作。"""

    def probe() -> str:
        try:
            db.query_one("SELECT 1")
        except Exception:  # noqa: BLE001 - 任何失敗都是「資料庫現在不能用」
            return DOWN
        return OK

    return probe


def llm_probe(
    traces,
    *,
    clock: Callable[[], float],
    window_seconds: float = 600.0,
    failure_ratio: float = 0.5,
) -> Callable[[], str]:
    """看最近一段時間內對話模型呼叫的失敗比例。**刻意不空打 Gemini**——那要花錢，
    而且一支公開端點每五秒燒一次 API 額度是荒謬的。

    近期沒有任何呼叫時回 unknown：沒有人講話的時候，談不上健康或不健康。
    """

    def probe() -> str:
        now = clock()
        stats = traces.get_overview_stats(
            today_start=now - window_seconds, hourly_start=now - window_seconds
        )
        calls = 0
        errors = 0
        for stage in stats.stages:
            if not stage.stage.startswith("llm:"):
                continue
            calls += stage.call_count
            errors += stage.error_count
        if calls == 0:
            return UNKNOWN
        return DOWN if errors / calls > failure_ratio else OK

    return probe


def scheduler_probe(
    schedule_state,
    specs,
    *,
    clock: Callable[[], datetime],
) -> Callable[[], str]:
    """排程器是否還在按時做事。

    ⚠️ **只看程序在不在會說謊**：2026-07-26 排程器假死七小時，`kinsun.sh status`
    全程顯示 RUNNING。判定必須看「工作有沒有按 cron 跑」，那樣程序被停掉、卡死、
    當掉三種情形都會浮現。判定邏輯與 `admin_jobs.py` 的逾期判定同源，看三個訊號：
    逾期未跑、從未執行過、一直在跑但一直失敗。

    ⚠️ 「從未執行過」分兩種情形，不可混為一談：**全部**工作都從未執行過回
    unknown——剛部署完還沒跑第一輪，不該一開機就報紅；但只要**有些**工作跑過、
    卻**還有**一支從未執行過，就必須回 down——排程器活著卻沒認領那支工作，是
    這裡看得到的情形裡最嚴重的一種，不能被別支正常運作的工作遮蔽掉。
    """
    default_tolerance = 300.0

    def probe() -> str:
        now = clock()
        seen_any = False
        any_never_ran = False
        for spec in specs:
            last = schedule_state.get_last_run(spec.name)
            if last is None:
                any_never_ran = True
                continue
            seen_any = True
            tolerance = (
                spec.max_lateness_seconds
                if spec.max_lateness_seconds is not None
                else default_tolerance
            )
            due_at = croniter(spec.cron, last).get_next(datetime)
            if (now - due_at).total_seconds() > tolerance:
                return DOWN
            # ⚠️ 「一直在跑、但一直失敗」是上面的逾期判定抓不到的盲區：`last_run_at`
            # 由 `_claim_if_due` 在執行**之前**寫入（at-most-once 搶占所必需），所以
            # 每輪都拋例外的工作照樣按時更新 last_run_at，逾期判定於是永遠是 False。
            # 要靠獨立的成功訊號才分得出來。
            #
            # `last_success` 為 None 有兩種可能：真的從沒成功過，或這一列是該欄
            # 上線前的舊資料。兩者都**不可**當成失敗——否則第一次部署整排變紅，
            # 狼來了一次之後就沒人再看這一頁了。故只在「有成功紀錄、但落後超過
            # 一個容許量」時才報。
            last_success = schedule_state.get_last_success(spec.name)
            is_failing = (
                last_success is not None
                and last is not None
                and (last - last_success).total_seconds() > tolerance
            )
            if is_failing:
                return DOWN

        if not seen_any:
            return UNKNOWN
        return DOWN if any_never_ran else OK

    return probe
