"""觀測後台操作面（spec 2026-07-12 §3.4，內測限定）：排程手動執行＋提醒立即發送。

與 admin.py（唯讀觀測）分檔：本檔的 POST 端點都會改變系統狀態，
需 X-Admin-Key＋INTERNAL_TESTING_ENABLED 雙重守門。
手動觸發直接呼叫與 scheduler worker 同一份 job 函式、不寫 scheduler_state，
不干擾 worker 的到期判斷。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun.accounts.service import AccountService
from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.appointments.store import AppointmentStore
from kinsun.channels.router import ChannelRouter
from kinsun.medications.jobs import build_medication_slot_job
from kinsun.medications.models import MedicationSlot
from kinsun.medications.store import MedicationStore
from kinsun.scheduler.scheduler import Job
from kinsun.scheduler.state import ScheduleStateStore
from kinsun.web.envelope import ok
from kinsun.web.routers.admin import build_require_admin


class DispatchReminderBody(BaseModel):
    kind: Literal["medication", "appointment"]
    slot: str | None = None


def create_admin_jobs_router(
    *,
    admin_api_key: str,
    internal_testing_enabled: bool,
    jobs: list[Job],
    schedule_state: ScheduleStateStore,
    accounts: AccountService,
    med_store: MedicationStore,
    appt_store: AppointmentStore,
    channel_router: ChannelRouter,
    record_reminder: Callable[[str, str, str], None],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(tags=["admin"])
    require_admin = build_require_admin(admin_api_key)

    def require_testing() -> None:
        if not internal_testing_enabled:
            raise HTTPException(status_code=403, detail="internal_testing_disabled")

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
            raise HTTPException(status_code=404, detail="job_not_found")
        job.run()  # 同步執行；內測工具，接受長任務佔用一個 worker thread
        return ok({"job_name": job.name, "ran_at": clock().timestamp()})

    @router.post(
        "/elders/{elder_id}/reminders/dispatch",
        dependencies=[Depends(require_admin), Depends(require_testing)],
    )
    def dispatch_reminder(elder_id: str, body: DispatchReminderBody) -> dict:
        if accounts.get_elder(elder_id) is None:
            raise HTTPException(status_code=404, detail="elder_not_found")
        if body.kind == "medication":
            try:
                slot = MedicationSlot(body.slot or "")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid_slot") from exc
            meds = [m for m in med_store.list_for_elder(elder_id) if slot in m.slots]
            build_medication_slot_job(
                slot=slot,
                meds_at_slot=lambda: meds,
                lookup_elder=accounts.get_elder,
                router=channel_router,
                hour=0,
                name=f"manual-medication-{slot.value}",
                record=record_reminder,
            ).run()
            return ok({"kind": "medication", "count": len(meds)})
        today = clock().date().isoformat()
        tomorrow = (clock().date() + timedelta(days=1)).isoformat()
        appts = {
            d: [a for a in appt_store.list_for_date(d) if a.elder_id == elder_id]
            for d in (today, tomorrow)
        }
        build_appointment_reminder_job(
            appts_on=lambda d: appts.get(d, []),
            today=lambda: today,
            tomorrow=lambda: tomorrow,
            lookup_elder=accounts.get_elder,
            guardians_of=accounts.guardians_of,
            router=channel_router,
            hour=0,
            name="manual-appointment",
            record=record_reminder,
        ).run()
        return ok({"kind": "appointment", "count": len(appts[today]) + len(appts[tomorrow])})

    return router
