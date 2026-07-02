"""用藥提醒服務（新增/查看/刪除）。"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from kinsun.medications.models import Medication, MedicationSlot
from kinsun.medications.store import MedicationStore


class MedicationService:
    def __init__(self, store: MedicationStore, *, new_id: Callable[[], str] | None = None) -> None:
        self._store = store
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    def save(self, elder_id: str, name: str, slots: tuple[MedicationSlot, ...]) -> Medication:
        med = Medication(self._new_id(), elder_id, name, tuple(slots))
        self._store.save(med)
        return med

    def list_for_elder(self, elder_id: str) -> list[Medication]:
        return self._store.list_for_elder(elder_id)

    def update(
        self, med_id: str, elder_id: str, name: str, slots: tuple[MedicationSlot, ...]
    ) -> Medication:
        med = Medication(med_id, elder_id, name, tuple(slots))
        self._store.save(med)
        return med

    def remove(self, med_id: str) -> None:
        self._store.remove(med_id)
