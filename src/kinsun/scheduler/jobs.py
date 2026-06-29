"""排程 job 組裝。"""

from __future__ import annotations

import logging
from collections.abc import Callable

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
    cron = f"{minute} {hour} * * *"

    def run() -> None:
        for session_id in sessions():
            try:
                run_one(session_id)
            except Exception:  # noqa: BLE001 - 單一 session 失敗不影響其他
                logger.exception("整理 session 失敗：%s", session_id)

    return Job(name=name, cron=cron, run=run)
