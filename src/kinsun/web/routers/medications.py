"""用藥資源：CRUD（家屬替長輩設定，金孫按時提醒）。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun.medications.models import SLOT_ORDER, MedicationSlot
from kinsun.medications.service import MedicationService
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class MedicationIn(BaseModel):
    name: str
    slots: list[str]


def _medication_json(med) -> dict:
    return {
        "medication_id": med.medication_id,
        "name": med.name,
        "slots": [s.value for s in med.slots],
    }


def create_medications_router(
    *,
    medications: MedicationService,
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
) -> APIRouter:
    router = APIRouter(tags=["medications"])

    def assert_medication_under_elder(elder_id: str, medication_id: str) -> None:
        if medication_id not in {m.medication_id for m in medications.list_for_elder(elder_id)}:
            raise HTTPException(status_code=404, detail="medication not found")

    def parse_slots(raw: list[str]) -> tuple[MedicationSlot, ...]:
        try:
            chosen = {MedicationSlot(s) for s in raw}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid slot") from exc
        if not chosen:
            raise HTTPException(status_code=400, detail="slots required")
        return tuple(s for s in SLOT_ORDER if s in chosen)

    @router.get("/elders/{elder_id}/medications")
    def list_medications(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        scope.assert_manages(auth, elder_id)
        return ok([_medication_json(m) for m in medications.list_for_elder(elder_id)])

    @router.post("/elders/{elder_id}/medications", status_code=201)
    def create_medication(
        elder_id: str, body: MedicationIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        slots = parse_slots(body.slots)
        return ok(_medication_json(medications.save(elder_id, name, slots)))

    @router.put("/elders/{elder_id}/medications/{medication_id}")
    def update_medication(
        elder_id: str,
        medication_id: str,
        body: MedicationIn,
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        assert_medication_under_elder(elder_id, medication_id)
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        slots = parse_slots(body.slots)
        return ok(_medication_json(medications.update(medication_id, elder_id, name, slots)))

    @router.delete("/elders/{elder_id}/medications/{medication_id}", status_code=204)
    def delete_medication(
        elder_id: str, medication_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> None:
        scope.assert_manages(auth, elder_id)
        assert_medication_under_elder(elder_id, medication_id)
        medications.remove(medication_id)

    return router
