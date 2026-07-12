"""回診資源：CRUD（今／明兩窗提醒的資料來源）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun.appointments.service import AppointmentService
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class AppointmentIn(BaseModel):
    date: str
    label: str


def _appointment_json(appt) -> dict:
    return {"appointment_id": appt.appointment_id, "date": appt.date, "label": appt.label}


def create_appointments_router(
    *,
    appointments: AppointmentService,
    clock: Callable[[], datetime],
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
) -> APIRouter:
    router = APIRouter(tags=["appointments"])

    def assert_appointment_under_elder(elder_id: str, appointment_id: str) -> None:
        if appointment_id not in {a.appointment_id for a in appointments.list_for_elder(elder_id)}:
            raise HTTPException(status_code=404, detail="appointment_not_found")

    def parse_appt_date(raw: str) -> str:
        try:
            parsed = datetime.strptime(raw.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_date") from exc
        if parsed < clock().date():
            raise HTTPException(status_code=400, detail="date_in_past")
        return parsed.isoformat()

    @router.get("/elders/{elder_id}/appointments")
    def list_appointments(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        scope.assert_manages(auth, elder_id)
        return ok([_appointment_json(a) for a in appointments.list_for_elder(elder_id)])

    @router.post("/elders/{elder_id}/appointments", status_code=201)
    def create_appointment(
        elder_id: str, body: AppointmentIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label_required")
        date = parse_appt_date(body.date)
        return ok(_appointment_json(appointments.save(elder_id, date, label)))

    @router.put("/elders/{elder_id}/appointments/{appointment_id}")
    def update_appointment(
        elder_id: str,
        appointment_id: str,
        body: AppointmentIn,
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        assert_appointment_under_elder(elder_id, appointment_id)
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label_required")
        date = parse_appt_date(body.date)
        return ok(_appointment_json(appointments.update(appointment_id, elder_id, date, label)))

    @router.delete("/elders/{elder_id}/appointments/{appointment_id}", status_code=204)
    def delete_appointment(
        elder_id: str, appointment_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> None:
        scope.assert_manages(auth, elder_id)
        assert_appointment_under_elder(elder_id, appointment_id)
        appointments.remove(appointment_id)

    return router
