"""家屬端 REST API（LIFF）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService
from kinsun.appointments.service import AppointmentService
from kinsun.medications.models import SLOT_ORDER, MedicationSlot
from kinsun.medications.service import MedicationService
from kinsun.reports.reminders import ReminderLogStore
from kinsun.safety.events import RiskEventStore
from kinsun.web.auth import AuthError, LiffVerifier


class MedicationIn(BaseModel):
    name: str
    slots: list[str]


class AppointmentIn(BaseModel):
    date: str
    label: str


class CreateElderIn(BaseModel):
    elder_name: str
    guardian_name: str = ""


def _med_json(med) -> dict:
    return {"med_id": med.med_id, "name": med.name, "slots": [s.value for s in med.slots]}


def _appt_json(appt) -> dict:
    return {"appt_id": appt.appt_id, "date": appt.date, "label": appt.label}


def create_api_router(
    *,
    verifier: LiffVerifier,
    accounts: AccountService,
    medications: MedicationService,
    appointments: AppointmentService,
    clock: Callable[[], datetime],
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    def current_guardian(authorization: str = Header(default="")) -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            return verifier.verify(token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc

    def assert_manages(line_user_id: str, elder_id: str) -> None:
        if elder_id not in {e.elder_id for e in accounts.elders_managed_by(line_user_id)}:
            raise HTTPException(status_code=404, detail="elder not found")

    def assert_med_under_elder(elder_id: str, med_id: str) -> None:
        if med_id not in {m.med_id for m in medications.list_for_elder(elder_id)}:
            raise HTTPException(status_code=404, detail="medication not found")

    def assert_appt_under_elder(elder_id: str, appt_id: str) -> None:
        if appt_id not in {a.appt_id for a in appointments.list_for_elder(elder_id)}:
            raise HTTPException(status_code=404, detail="appointment not found")

    def parse_slots(raw: list[str]) -> tuple[MedicationSlot, ...]:
        try:
            chosen = {MedicationSlot(s) for s in raw}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid slot") from exc
        if not chosen:
            raise HTTPException(status_code=400, detail="slots required")
        return tuple(s for s in SLOT_ORDER if s in chosen)

    def parse_appt_date(raw: str) -> str:
        try:
            parsed = datetime.strptime(raw.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid date") from exc
        if parsed < clock().date():
            raise HTTPException(status_code=400, detail="date in past")
        return parsed.isoformat()

    @router.get("/me/elders")
    def my_elders(line_user_id: str = Depends(current_guardian)) -> dict:
        elders = accounts.elders_managed_by(line_user_id)
        return {"elders": [{"elder_id": e.elder_id, "name": e.name} for e in elders]}

    @router.post("/elders", status_code=201)
    def create_elder(body: CreateElderIn, line_user_id: str = Depends(current_guardian)) -> dict:
        name = body.elder_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="elder_name required")
        elder = accounts.create_elder(line_user_id, body.guardian_name, name)
        invite = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
        return {"elder_id": elder.elder_id, "name": elder.name, "invite_code": invite.code}

    @router.post("/elders/{elder_id}/guardian-invites", status_code=201)
    def create_guardian_invite(
        elder_id: str, line_user_id: str = Depends(current_guardian)
    ) -> dict:
        assert_manages(line_user_id, elder_id)
        invite = accounts.generate_invite(elder_id, InviteRole.GUARDIAN)
        return {"invite_code": invite.code}

    @router.get("/elders/{elder_id}/medications")
    def list_medications(elder_id: str, line_user_id: str = Depends(current_guardian)) -> dict:
        assert_manages(line_user_id, elder_id)
        return {"medications": [_med_json(m) for m in medications.list_for_elder(elder_id)]}

    @router.post("/elders/{elder_id}/medications", status_code=201)
    def add_medication(
        elder_id: str, body: MedicationIn, line_user_id: str = Depends(current_guardian)
    ) -> dict:
        assert_manages(line_user_id, elder_id)
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        slots = parse_slots(body.slots)
        return _med_json(medications.add(elder_id, name, slots))

    @router.put("/elders/{elder_id}/medications/{med_id}")
    def update_medication(
        elder_id: str,
        med_id: str,
        body: MedicationIn,
        line_user_id: str = Depends(current_guardian),
    ) -> dict:
        assert_manages(line_user_id, elder_id)
        assert_med_under_elder(elder_id, med_id)
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        slots = parse_slots(body.slots)
        return _med_json(medications.update(med_id, elder_id, name, slots))

    @router.delete("/elders/{elder_id}/medications/{med_id}", status_code=204)
    def delete_medication(
        elder_id: str, med_id: str, line_user_id: str = Depends(current_guardian)
    ) -> None:
        assert_manages(line_user_id, elder_id)
        assert_med_under_elder(elder_id, med_id)
        medications.remove(med_id)

    @router.get("/elders/{elder_id}/appointments")
    def list_appointments(elder_id: str, line_user_id: str = Depends(current_guardian)) -> dict:
        assert_manages(line_user_id, elder_id)
        return {"appointments": [_appt_json(a) for a in appointments.list_for_elder(elder_id)]}

    @router.post("/elders/{elder_id}/appointments", status_code=201)
    def add_appointment(
        elder_id: str, body: AppointmentIn, line_user_id: str = Depends(current_guardian)
    ) -> dict:
        assert_manages(line_user_id, elder_id)
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label required")
        date = parse_appt_date(body.date)
        return _appt_json(appointments.add(elder_id, date, label))

    @router.put("/elders/{elder_id}/appointments/{appt_id}")
    def update_appointment(
        elder_id: str,
        appt_id: str,
        body: AppointmentIn,
        line_user_id: str = Depends(current_guardian),
    ) -> dict:
        assert_manages(line_user_id, elder_id)
        assert_appt_under_elder(elder_id, appt_id)
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label required")
        date = parse_appt_date(body.date)
        return _appt_json(appointments.update(appt_id, elder_id, date, label))

    @router.delete("/elders/{elder_id}/appointments/{appt_id}", status_code=204)
    def delete_appointment(
        elder_id: str, appt_id: str, line_user_id: str = Depends(current_guardian)
    ) -> None:
        assert_manages(line_user_id, elder_id)
        assert_appt_under_elder(elder_id, appt_id)
        appointments.remove(appt_id)

    @router.get("/elders/{elder_id}/health-report")
    def health_report(elder_id: str, line_user_id: str = Depends(current_guardian)) -> dict:
        assert_manages(line_user_id, elder_id)
        cutoff = (clock() - timedelta(days=30)).timestamp()
        elder = accounts.get_elder(elder_id)
        session_id = elder.line_user_id if elder else None
        risks = (
            [e for e in risk_events.list_for_session(session_id) if e.created_at >= cutoff]
            if session_id
            else []
        )
        reminders = [r for r in reminder_logs.list_for_elder(elder_id) if r.created_at >= cutoff]
        return {
            "risk_events": [
                {"tier": int(e.tier), "reason": e.reason, "created_at": e.created_at} for e in risks
            ],
            "reminders": [
                {"kind": r.kind, "content": r.content, "created_at": r.created_at}
                for r in reminders
            ],
        }

    return router
