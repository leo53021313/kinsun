"""用藥提醒儲存：Protocol 與 Postgres 實作。"""

from __future__ import annotations

from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.medications.models import Medication, MedicationSlot


class MedicationError(Exception):
    """用藥資料讀寫失敗。"""


class MedicationStore(Protocol):
    def save(self, med: Medication) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[Medication]: ...
    def list_for_slot(self, slot: MedicationSlot) -> list[Medication]: ...
    def remove(self, medication_id: str) -> None: ...


class PgMedicationStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: MedicationError(f"用藥資料存取失敗：{m}"))

    def _to_med(self, row: tuple) -> Medication:
        medication_id, elder_id, name, slots = row
        parsed = tuple(MedicationSlot(s) for s in slots.split(","))
        return Medication(medication_id, elder_id, name, parsed)

    def save(self, med: Medication) -> None:
        self._db.execute(
            "INSERT INTO medications (medication_id, elder_id, name, slots) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (medication_id) DO UPDATE SET "
            "elder_id = EXCLUDED.elder_id, name = EXCLUDED.name, slots = EXCLUDED.slots",
            (med.medication_id, med.elder_id, med.name, ",".join(s.value for s in med.slots)),
        )

    def list_for_elder(self, elder_id: str) -> list[Medication]:
        rows = self._db.query(
            "SELECT medication_id, elder_id, name, slots FROM medications "
            "WHERE elder_id = %s ORDER BY name",
            (elder_id,),
        )
        return [self._to_med(r) for r in rows]

    def list_for_slot(self, slot: MedicationSlot) -> list[Medication]:
        # LIKE 僅作粗篩以縮小掃描；再於 Python 精確比對集合成員，
        # 使結果與 FakeMedicationStore 對任何 slot 值都等價（不因子字串誤命中）。
        rows = self._db.query(
            "SELECT medication_id, elder_id, name, slots FROM medications WHERE slots LIKE %s",
            (f"%{slot.value}%",),
        )
        meds = [self._to_med(r) for r in rows]
        return [m for m in meds if slot in m.slots]

    def remove(self, medication_id: str) -> None:
        self._db.execute("DELETE FROM medications WHERE medication_id = %s", (medication_id,))


class FakeMedicationStore:
    """MedicationStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._meds: dict[str, Medication] = {}

    def save(self, med: Medication) -> None:
        self._meds[med.medication_id] = med

    def list_for_elder(self, elder_id: str) -> list[Medication]:
        rows = [m for m in self._meds.values() if m.elder_id == elder_id]
        return sorted(rows, key=lambda m: m.name)

    def list_for_slot(self, slot: MedicationSlot) -> list[Medication]:
        return [m for m in self._meds.values() if slot in m.slots]

    def remove(self, medication_id: str) -> None:
        self._meds.pop(medication_id, None)
