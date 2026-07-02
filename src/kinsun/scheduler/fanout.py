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
    hour: int,
    population: Callable[[], Iterable[T]],
    action: Callable[[T], None],
    minute: int = 0,
    item_id: Callable[[T], str] = str,
    logger: logging.Logger = logger,
) -> Job:
    """組一個每日 cron job：遍歷 population()，對每筆呼叫 action，逐筆隔離失敗。

    過濾/守門請在 action 內提早 return；母體前處理（分組等）請在 population 內完成。
    """
    cron = f"{minute} {hour} * * *"

    def run() -> None:
        for item in population():
            try:
                action(item)
            except Exception:  # noqa: BLE001 - 單一對象失敗不影響其他
                logger.exception("job %s 處理失敗：%s", name, item_id(item))

    return Job(name=name, cron=cron, run=run)
