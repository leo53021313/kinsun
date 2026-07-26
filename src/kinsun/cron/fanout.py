"""扇出執行器：每天某點遍歷一個母體，逐筆隔離失敗。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TypeVar

from kinsun import tracing
from kinsun.cron.scheduler import Job

logger = logging.getLogger("kinsun.cron")

T = TypeVar("T")


def fanout_job(  # noqa: UP047
    *,
    name: str,
    hour: int | None = None,
    population: Callable[[], Iterable[T]],
    action: Callable[[T], None],
    minute: int = 0,
    cron: str | None = None,
    item_id: Callable[[T], str] = str,
    max_lateness_seconds: float | None = None,
    logger: logging.Logger = logger,
) -> Job:
    """組一個 cron job：遍歷 population()，對每筆呼叫 action，逐筆隔離失敗。

    過濾/守門請在 action 內提早 return；母體前處理（分組等）請在 population 內完成。

    排程時間二選一，且必須恰好給一個：
    - `hour`（＋選用的 `minute`）＝ 每天某一點，絕大多數 job 用這個。
    - `cron` ＝ 直接給完整 cron 字面，供 hour／minute 組不出來的頻率使用
      （自適應問候時間每半小時掃一次，spec 2026-07-16）。

    兩個都給時哪個生效無從得知，靜默採用其一等於讓 job 在不明的時刻跑——故快速失敗。
    """
    if (hour is None) == (cron is None):
        raise ValueError(f"fanout_job（{name}）需要 hour 或 cron 其中之一，不可都給或都不給。")
    schedule = cron if cron is not None else f"{minute} {hour} * * *"

    # 每一筆處理＝一條 Opik root trace（工程觀測，OPIK_ENABLED 才生效）。內層 flow
    # （proactive_turn／nightly_reflection 等）本來各自是無根 trace，掛進本 root 後
    # 自然收斂為子 span；純提醒 job（用藥／回診，無 LLM）也因此首次可觀測。
    # 停用時 @track 退化為直呼 action，run() 的逐筆隔離語意一字不差。
    @tracing.track(name=name, type="general", capture_input=False, capture_output=False)
    def run_item(item: T) -> None:
        tracing.update_trace_metadata(job=name, item=item_id(item))
        action(item)

    def run() -> None:
        for item in population():
            try:
                run_item(item)
            except Exception:  # noqa: BLE001 - 單一對象失敗不影響其他
                logger.exception("job %s 處理失敗：%s", name, item_id(item))

    return Job(name=name, cron=schedule, run=run, max_lateness_seconds=max_lateness_seconds)
