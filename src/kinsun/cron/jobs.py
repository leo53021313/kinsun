"""排程 job 組裝。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.cron.fanout import fanout_job
from kinsun.cron.scheduler import Job

logger = logging.getLogger("kinsun.cron")


def build_consolidation_job(
    *,
    sessions: Callable[[], list[str]],
    run_one: Callable[[str], object],
    cron: str,
    name: str = "daily-consolidation",
) -> Job:
    # 全庫唯一開啟配額退避的 job（2026-07-27）。兩個前提都成立才敢開：
    # (1) 它是實際被打到的那一支——logs/scheduler.log 的 15 筆 RESOURCE_EXHAUSTED 全在這裡
    #     （路徑 fanout → consolidation → mem0.add → Gemini embedder）；
    # (2) 它本身冪等——已整理過的日以 memory_consolidations 標記跳過（✅ 庚-13／A-19），
    #     重跑不會把同一天的對話寫進長期記憶兩次。
    # ⚠️ 問候與提醒 job **不可**比照辦理：那些重試會讓長輩收到重複訊息。
    return fanout_job(
        name=name,
        cron=cron,
        population=sessions,
        action=run_one,
        retry_quota_attempts=3,
        logger=logger,
    )


def build_audio_cleanup_job(
    *,
    cleanup: Callable[[], None],
    cron: str,
    name: str = "audio-cleanup",
) -> Job:
    return Job(name=name, cron=cron, run=cleanup)
