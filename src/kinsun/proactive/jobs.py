"""主動關懷的排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.proactive")

GREETING_INTENT = "早安問候，關心長者今天的狀況"
INACTIVITY_INTENT = "長者已經一段時間沒有互動了，主動表達想念與關心"


def build_greeting_job(
    *,
    sessions: Callable[[], list[str]],
    greet_one: Callable[[str], object],
    hour: int,
    minute: int = 0,
    name: str = "daily-greeting",
) -> Job:
    return fanout_job(
        name=name, hour=hour, minute=minute, population=sessions, action=greet_one, logger=logger
    )


def build_inactivity_job(
    *,
    sessions: Callable[[], list[str]],
    last_active: Callable[[str], float | None],
    clock: Callable[[], datetime],
    threshold_seconds: float,
    care_one: Callable[[str], object],
    hour: int,
    minute: int = 0,
    name: str = "inactivity-care",
) -> Job:
    def action(session_id: str) -> None:
        last = last_active(session_id)
        if last is not None and clock().timestamp() - last >= threshold_seconds:
            care_one(session_id)

    return fanout_job(
        name=name, hour=hour, minute=minute, population=sessions, action=action, logger=logger
    )
