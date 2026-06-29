"""排程 job 組裝。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.scheduler")


def build_consolidation_job(
    *,
    sessions: Callable[[], list[str]],
    run_one: Callable[[str], object],
    hour: int,
    minute: int = 0,
    name: str = "daily-consolidation",
) -> Job:
    return fanout_job(
        name=name, hour=hour, minute=minute, population=sessions, action=run_one, logger=logger
    )
