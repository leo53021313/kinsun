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
                claimed = self._claim_if_due(job, now)
            except Exception:  # noqa: BLE001 - 狀態讀取/解析失敗不影響其他 job
                logger.exception("排程到期判斷失敗：%s", job.name)
                continue
            if not claimed:
                continue
            try:
                job.run()
            except Exception:  # noqa: BLE001 - 排程不可因單一 job 崩潰
                logger.exception("排程 job 失敗：%s", job.name)
            ran.append(job.name)
        return ran

    def _claim_if_due(self, job: Job, now: datetime) -> bool:
        """到期則原子搶占（✅ 庚-17／A-42）：執行前先以「現值仍為我讀到的 last」
        條件更新狀態，搶到才跑——誤起雙 worker 時同一 job 只執行一次。
        搶占＝寫入 last_run，故 job 失敗也算已跑（與舊「跑完才寫」語意一致）。"""
        last = self._state.get_last_run(job.name)
        if last is None:  # 首見：種基準，下一次 cron 時間才觸發
            self._state.set_last_run(job.name, now)
            return False
        if croniter(job.cron, last).get_next(datetime) > now:
            return False
        return self._state.try_claim(job.name, expected=last, now=now)
