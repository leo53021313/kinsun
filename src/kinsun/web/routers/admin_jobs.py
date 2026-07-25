"""觀測後台操作面（spec 2026-07-12 §3.4，內測限定）：排程手動執行＋提醒立即發送。

與 admin.py（唯讀觀測）分檔：本檔的 POST 端點都會改變系統狀態，
需 X-Admin-Key＋INTERNAL_TESTING_ENABLED 雙重守門。
手動觸發直接呼叫與 scheduler worker 同一份 job 函式、不寫 scheduler_state，
不干擾 worker 的到期判斷。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun import tracing
from kinsun.accounts.service import AccountService
from kinsun.channels.router import ChannelRouter
from kinsun.scheduler.scheduler import Job
from kinsun.scheduler.state import ScheduleStateStore
from kinsun.schedules.jobs import build_schedule_dispatch_job
from kinsun.schedules.models import RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import ScheduleStore
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.admin import build_require_admin


class DispatchReminderBody(BaseModel):
    kind: Literal["medication", "appointment", "custom"]


class _ForcedDueStore:
    """讓派送 job 把某位長輩某一類的排程「當成現在到期」，供後台手動觸發。

    ⚠ mark_fired／mark_settled 刻意 **no-op**：手動觸發是內測工具，若讓它寫進真正的
    狀態欄，長輩當天真正該收到的那一則就不會發了——測試動作不可以吃掉正式提醒。
    """

    def __init__(self, inner: ScheduleStore, *, elder_id: str, kind: ScheduleKind) -> None:
        self._rows = [s for s in inner.list_for_elder(elder_id) if s.kind == kind]

    def list_due_once(self, *, until: float) -> list[Schedule]:
        return [s for s in self._rows if s.repeat_kind == RepeatKind.ONCE]

    def list_due_repeating(self, **kwargs) -> list[Schedule]:
        return [s for s in self._rows if s.repeat_kind != RepeatKind.ONCE]

    def mark_fired(self, schedule_id: str, *, now: float) -> None:
        return None

    def mark_settled(self, schedule_id: str, *, now: float) -> None:
        return None


# 手動觸發的 Opik root trace（工程觀測，OPIK_ENABLED 才生效）。FastAPI handler 因
# 依賴注入需保留原 signature，不能直接貼 @track，故把實際執行抽到這兩個 helper：
# worker 排程走 fanout 各自成 root，後台觸發則統一掛在此 root 下、標記為 admin 通道。
@tracing.track(name="admin_run_job", type="general", capture_input=False, capture_output=False)
def _run_job_traced(job: Job) -> None:
    tracing.tag_current_trace(channel="admin", job=job.name)
    job.run()


@tracing.track(
    name="admin_dispatch_reminder", type="general", capture_input=False, capture_output=False
)
def _dispatch_reminder_traced(job: Job, *, elder_id: str, kind: str) -> None:
    tracing.tag_current_trace(elder_id=elder_id, channel="admin", kind=kind)
    job.run()


def create_admin_jobs_router(
    *,
    admin_api_key: str,
    internal_testing_enabled: bool,
    jobs: list[Job],
    schedule_state: ScheduleStateStore,
    accounts: AccountService,
    schedule_store: ScheduleStore,
    channel_router: ChannelRouter,
    record_reminder: Callable[[str, str, str], None],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(tags=["admin"])
    require_admin = build_require_admin(admin_api_key)

    def require_testing() -> None:
        if not internal_testing_enabled:
            raise HTTPException(status_code=403, detail=ErrorCode.INTERNAL_TESTING_DISABLED)

    @router.get("/jobs", dependencies=[Depends(require_admin)])
    def list_jobs() -> dict:
        items = []
        for job in jobs:
            last = schedule_state.get_last_run(job.name)
            items.append(
                {
                    "job_name": job.name,
                    "cron": job.cron,
                    "last_run_at": last.timestamp() if last else None,
                }
            )
        return ok(items)

    @router.post(
        "/jobs/{job_name}/run",
        dependencies=[Depends(require_admin), Depends(require_testing)],
    )
    def run_job(job_name: str) -> dict:
        job = next((j for j in jobs if j.name == job_name), None)
        if job is None:
            raise HTTPException(status_code=404, detail=ErrorCode.JOB_NOT_FOUND)
        _run_job_traced(job)  # 同步執行；內測工具，接受長任務佔用一個 worker thread
        return ok({"job_name": job.name, "ran_at": clock().timestamp()})

    @router.post(
        "/elders/{elder_id}/reminders/dispatch",
        dependencies=[Depends(require_admin), Depends(require_testing)],
    )
    def dispatch_reminder(elder_id: str, body: DispatchReminderBody) -> dict:
        if accounts.get_elder(elder_id) is None:
            raise HTTPException(status_code=404, detail=ErrorCode.ELDER_NOT_FOUND)
        kind = ScheduleKind(body.kind)
        forced = _ForcedDueStore(schedule_store, elder_id=elder_id, kind=kind)
        job = build_schedule_dispatch_job(
            store=forced,
            lookup_elder=accounts.get_elder,
            guardians_of=accounts.guardians_of,
            router=channel_router,
            clock=clock,
            record=record_reminder,
            name=f"manual-{body.kind}",
        )
        _dispatch_reminder_traced(job, elder_id=elder_id, kind=body.kind)
        count = len(forced.list_due_once(until=0)) + len(forced.list_due_repeating())
        return ok({"kind": body.kind, "count": count})

    return router
