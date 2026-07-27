"""觀測資料清理的排程 job。"""

from __future__ import annotations

from collections.abc import Callable

from kinsun.cron.scheduler import Job


def build_observability_cleanup_job(
    *,
    purge: Callable[[], None],
    cron: str,
    name: str = "observability-cleanup",
) -> Job:
    return Job(name=name, cron=cron, run=purge)
