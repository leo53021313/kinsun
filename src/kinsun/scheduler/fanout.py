"""扇出執行器：每天某點遍歷一個母體，逐筆隔離失敗。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TypeVar

from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.scheduler")

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

    def run() -> None:
        for item in population():
            try:
                action(item)
            except Exception:  # noqa: BLE001 - 單一對象失敗不影響其他
                logger.exception("job %s 處理失敗：%s", name, item_id(item))

    return Job(name=name, cron=schedule, run=run)
