"""公開運營狀態端點（spec 2026-07-30 W-03）：`GET /api/v1/demo-status`。

網頁版前端一進站就打這一支，據此決定「開始使用」按鈕能不能按。

⚠️ **公開、不需認證**，所以只回粗粒度狀態：分項一律是四個字面值之一，
不含版本、主機名、埠號或例外訊息——那些對前端沒有用，對掃描的人很有用。

⚠️ **結果快取**：有人壓著重整就會把 ASR 與 TTS 的 healthz 打爆，那正是這一頁
要偵測的服務。快取讓探測頻率與請求頻率脫鉤。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping

from fastapi import APIRouter

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
