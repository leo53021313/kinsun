"""回診提醒儲存：Protocol 與 Postgres 實作。"""

from __future__ import annotations

from typing import Protocol

from kinsun.appointments.models import Appointment
from kinsun.db import Database, _Errors


class AppointmentError(Exception):
    """回診資料讀寫失敗。"""


class AppointmentStore(Protocol):
    def save(self, appt: Appointment) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[Appointment]: ...
    def list_for_date(self, date: str) -> list[Appointment]: ...
    def remove(self, appointment_id: str) -> None: ...


class PgAppointmentStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: AppointmentError(f"回診資料存取失敗：{m}"))

    def _to_appt(self, row: tuple) -> Appointment:
        appointment_id, elder_id, date, label, time = row
        return Appointment(appointment_id, elder_id, date, label, time)

    def save(self, appt: Appointment) -> None:
        self._db.execute(
            "INSERT INTO appointments (appointment_id, elder_id, date, label, time) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (appointment_id) DO UPDATE SET "
            "elder_id = EXCLUDED.elder_id, date = EXCLUDED.date, "
            "label = EXCLUDED.label, time = EXCLUDED.time",
            (appt.appointment_id, appt.elder_id, appt.date, appt.label, appt.time),
        )

    def list_for_elder(self, elder_id: str) -> list[Appointment]:
        rows = self._db.query(
            "SELECT appointment_id, elder_id, date, label, time FROM appointments "
            "WHERE elder_id = %s ORDER BY date, time",
            (elder_id,),
        )
        return [self._to_appt(r) for r in rows]

    def list_for_date(self, date: str) -> list[Appointment]:
        rows = self._db.query(
            "SELECT appointment_id, elder_id, date, label, time FROM appointments WHERE date = %s",
            (date,),
        )
        return [self._to_appt(r) for r in rows]

    def remove(self, appointment_id: str) -> None:
        self._db.execute("DELETE FROM appointments WHERE appointment_id = %s", (appointment_id,))


class FakeAppointmentStore:
    """AppointmentStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._appts: dict[str, Appointment] = {}

    def save(self, appt: Appointment) -> None:
        self._appts[appt.appointment_id] = appt

    def list_for_elder(self, elder_id: str) -> list[Appointment]:
        rows = [a for a in self._appts.values() if a.elder_id == elder_id]
        return sorted(rows, key=lambda a: (a.date, a.time))

    def list_for_date(self, date: str) -> list[Appointment]:
        return [a for a in self._appts.values() if a.date == date]

    def remove(self, appointment_id: str) -> None:
        self._appts.pop(appointment_id, None)
