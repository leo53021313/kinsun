"""自建輕量排程器：croniter 完整 cron + 狀態持久化 + 補跨一次。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from croniter import croniter

from kinsun.scheduler.state import ScheduleStateStore

logger = logging.getLogger("kinsun.scheduler")


@dataclass(frozen=True)
class Job:
    name: str
    cron: str
    run: Callable[[], None]


class Scheduler:
    def __init__(
        self,
        jobs: list[Job],
        clock: Callable[[], datetime],
        state: ScheduleStateStore,
    ) -> None:
        self._jobs = jobs
        self._clock = clock
        self._state = state

    def run_due(self) -> list[str]:
        now = self._clock()
        ran: list[str] = []
        for job in self._jobs:
            try:
                due = self._is_due(job, now)
            except Exception:  # noqa: BLE001 - 狀態讀取/解析失敗不影響其他 job
                logger.exception("排程到期判斷失敗：%s", job.name)
                continue
            if not due:
                continue
            try:
                job.run()
            except Exception:  # noqa: BLE001 - 排程不可因單一 job 崩潰
                logger.exception("排程 job 失敗：%s", job.name)
            try:
                self._state.set_last_run(job.name, now)
            except Exception:  # noqa: BLE001
                logger.exception("排程狀態寫入失敗：%s", job.name)
            ran.append(job.name)
        return ran

    def _is_due(self, job: Job, now: datetime) -> bool:
        last = self._state.get_last_run(job.name)
        if last is None:  # 首見：種基準，下一次 cron 時間才觸發
            self._state.set_last_run(job.name, now)
            return False
        return croniter(job.cron, last).get_next(datetime) <= now
