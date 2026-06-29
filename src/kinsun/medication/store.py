"""用藥提醒儲存：Protocol 與 Postgres 實作。"""

from __future__ import annotations

from typing import Protocol

from kinsun.accounts.repository import AccountError
from kinsun.db import connect
from kinsun.medication.models import Medication, MedicationSlot


class MedicationStore(Protocol):
    def add(self, med: Medication) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[Medication]: ...
    def list_for_slot(self, slot: MedicationSlot) -> list[Medication]: ...
    def remove(self, med_id: str) -> None: ...


class PgMedicationStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _to_med(self, row: tuple) -> Medication:
        med_id, elder_id, name, slots = row
        parsed = tuple(MedicationSlot(s) for s in slots.split(","))
        return Medication(med_id, elder_id, name, parsed)

    def add(self, med: Medication) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute(
                    "INSERT INTO medications (med_id, elder_id, name, slots) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (med_id) DO UPDATE SET "
                    "elder_id = EXCLUDED.elder_id, name = EXCLUDED.name, slots = EXCLUDED.slots",
                    (med.med_id, med.elder_id, med.name, ",".join(s.value for s in med.slots)),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"寫入用藥失敗：{exc}") from exc

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        try:
            with connect(self._url) as conn:
                return conn.execute(sql, params).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"讀取用藥失敗：{exc}") from exc

    def list_for_elder(self, elder_id: str) -> list[Medication]:
        rows = self._query(
            "SELECT med_id, elder_id, name, slots FROM medications "
            "WHERE elder_id = %s ORDER BY name",
            (elder_id,),
        )
        return [self._to_med(r) for r in rows]

    def list_for_slot(self, slot: MedicationSlot) -> list[Medication]:
        rows = self._query(
            "SELECT med_id, elder_id, name, slots FROM medications WHERE slots LIKE %s",
            (f"%{slot.value}%",),
        )
        return [self._to_med(r) for r in rows]

    def remove(self, med_id: str) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute("DELETE FROM medications WHERE med_id = %s", (med_id,))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"刪除用藥失敗：{exc}") from exc
