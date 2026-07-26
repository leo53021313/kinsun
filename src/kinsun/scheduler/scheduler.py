"""自建輕量排程器：croniter 完整 cron + 狀態持久化 + 補跨一次。"""

from __future__ import annotations

import logging
import threading
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
    background: bool = False
    """長跑 job：丟到獨立執行緒，不佔住掃描迴圈。

    ⚠️ 為什麼需要（2026-07-26 實測）：`run_due` 是逐一同步執行，一個慢 job 會讓
    **整輪掃描停住**。當晚 `daily-consolidation` 對 39 位長輩跑整理＋摘要＋反思時，
    每分鐘該派送的 `schedule-dispatch` 整整兩分鐘沒有動——長輩人數再多一些，
    吃藥提醒就會遲到十幾分鐘，而那正是這個系統最不該遲到的東西。

    標記在 `worker.build_jobs`（組裝點）而非各工廠：一個 job 會不會塞住掃描，
    取決於它要遍歷多少長輩，那是部署面的性質，不是工廠的性質。
    """


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
        # 背景 job 的在途執行緒；用來防止同一個 job 疊跑（見 run_due）。
        self._inflight: dict[str, threading.Thread] = {}

    def run_due(self) -> list[str]:
        """掃一輪，把到期的 job 跑掉；回傳本輪啟動的 job 名。

        `background=True` 的 job 只負責**啟動**就回來，不等它跑完——否則一個長跑
        批次會把整輪掃描連同後面所有 job 一起卡住（2026-07-26 實測：夜間批次跑的
        兩分鐘內，每分鐘該派送的 `schedule-dispatch` 完全沒有動）。
        """
        now = self._clock()
        ran: list[str] = []
        for job in self._jobs:
            # 上一輪還在跑就整個跳過——**連認領都不做**。認領會把 last_run_at 推到
            # 現在，等於謊稱「這一輪跑過了」；而真正該表達的是「這一輪不必再跑，
            # 因為上一輪還沒結束」。at-most-once 的語意在這裡才成立。
            if job.background and self._is_inflight(job.name):
                logger.info("排程 job %s 上一輪尚未結束，本輪跳過", job.name)
                continue
            try:
                claimed = self._claim_if_due(job, now)
            except Exception:  # noqa: BLE001 - 狀態讀取/解析失敗不影響其他 job
                logger.exception("排程到期判斷失敗：%s", job.name)
                continue
            if not claimed:
                continue
            if job.background:
                self._start_background(job)
            else:
                try:
                    job.run()
                except Exception:  # noqa: BLE001 - 排程不可因單一 job 崩潰
                    logger.exception("排程 job 失敗：%s", job.name)
            ran.append(job.name)
        return ran

    def _is_inflight(self, name: str) -> bool:
        thread = self._inflight.get(name)
        return thread is not None and thread.is_alive()

    def _start_background(self, job: Job) -> None:
        """把 job 丟到獨立的守護執行緒。

        用 daemon=True 而非執行緒池：排程器停止時（SIGTERM／看門狗自我了結）不該被
        一個跑到一半的夜間批次拖住——`ThreadPoolExecutor` 的工作執行緒非 daemon，
        直譯器結束時會等它跑完，`kinsun.sh stop` 會因此看起來像當掉。
        批次本身逐筆隔離失敗且冪等（整理有 consolidation_log 逐日標記），
        中途被砍掉下一輪會補上。
        """

        def _run() -> None:
            try:
                job.run()
            except Exception:  # noqa: BLE001 - 背景 job 崩潰不可影響掃描迴圈
                logger.exception("排程 job 失敗：%s", job.name)

        thread = threading.Thread(target=_run, name=f"kinsun-job-{job.name}", daemon=True)
        self._inflight[job.name] = thread
        thread.start()

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
