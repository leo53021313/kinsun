"""自建輕量排程器。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger("kinsun.scheduler")


@dataclass(frozen=True)
class Job:
    name: str
    hour: int
    minute: int
    run: Callable[[], None]


class Scheduler:
    def __init__(self, jobs: list[Job], clock: Callable[[], datetime]) -> None:
        self._jobs = jobs
        self._clock = clock
        self._last_run: dict[str, date] = {}

    def run_due(self) -> list[str]:
        now = self._clock()
        ran: list[str] = []
        for job in self._jobs:
            if not self._is_due(job, now):
                continue
            try:
                job.run()
            except Exception:  # noqa: BLE001 - 排程不可因單一 job 崩潰
                logger.exception("排程 job 失敗：%s", job.name)
            self._last_run[job.name] = now.date()
            ran.append(job.name)
        return ran

    def _is_due(self, job: Job, now: datetime) -> bool:
        if self._last_run.get(job.name) == now.date():
            return False
        return (now.hour, now.minute) >= (job.hour, job.minute)
