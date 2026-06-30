"""家屬端 REST API（LIFF）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from kinsun.accounts.service import AccountService
from kinsun.medication.models import SLOT_ORDER, MedicationSlot
from kinsun.medication.service import MedicationService
from kinsun.web.auth import AuthError, LiffVerifier


class MedicationIn(BaseModel):
    name: str
    slots: list[str]


def _med_json(med) -> dict:
    return {"med_id": med.med_id, "name": med.name, "slots": [s.value for s in med.slots]}


def create_api_router(
    *, verifier: LiffVerifier, accounts: AccountService, medications: MedicationService
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

    def parse_slots(raw: list[str]) -> tuple[MedicationSlot, ...]:
        try:
            chosen = {MedicationSlot(s) for s in raw}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid slot") from exc
        if not chosen:
            raise HTTPException(status_code=400, detail="slots required")
        return tuple(s for s in SLOT_ORDER if s in chosen)

    @router.get("/me/elders")
    def my_elders(line_user_id: str = Depends(current_guardian)) -> dict:
        elders = accounts.elders_managed_by(line_user_id)
        return {"elders": [{"elder_id": e.elder_id, "name": e.name} for e in elders]}

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

    return router
