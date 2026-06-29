"""主動關懷的排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

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
    cron = f"{minute} {hour} * * *"

    def run() -> None:
        for session_id in sessions():
            try:
                greet_one(session_id)
            except Exception:  # noqa: BLE001 - 單一長者失敗不影響其他
                logger.exception("問候 session 失敗：%s", session_id)

    return Job(name=name, cron=cron, run=run)


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
    cron = f"{minute} {hour} * * *"

    def run() -> None:
        now_ts = clock().timestamp()
        for session_id in sessions():
            try:
                last = last_active(session_id)
                if last is not None and now_ts - last >= threshold_seconds:
                    care_one(session_id)
            except Exception:  # noqa: BLE001 - 單一長者失敗不影響其他
                logger.exception("失聯關心 session 失敗：%s", session_id)

    return Job(name=name, cron=cron, run=run)
