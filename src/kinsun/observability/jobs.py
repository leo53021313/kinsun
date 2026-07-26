"""觀測資料清理的排程 job。"""

from __future__ import annotations

from collections.abc import Callable

from kinsun.cron.scheduler import Job


def build_observability_cleanup_job(
    *,
    purge: Callable[[], None],
    hour: int,
    minute: int = 45,
    name: str = "observability-cleanup",
) -> Job:
    return Job(name=name, cron=f"{minute} {hour} * * *", run=purge)
