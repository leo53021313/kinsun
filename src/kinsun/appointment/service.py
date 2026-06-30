"""回診提醒服務（新增/查看/upcoming/刪除）。"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from kinsun.appointment.models import Appointment
from kinsun.appointment.store import AppointmentStore


class AppointmentService:
    def __init__(self, store: AppointmentStore, *, new_id: Callable[[], str] | None = None) -> None:
        self._store = store
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    def add(self, elder_id: str, date: str, label: str) -> Appointment:
        appt = Appointment(self._new_id(), elder_id, date, label)
        self._store.add(appt)
        return appt

    def list_for_elder(self, elder_id: str) -> list[Appointment]:
        return self._store.list_for_elder(elder_id)

    def upcoming(self, elder_id: str, today: str) -> list[Appointment]:
        return [a for a in self._store.list_for_elder(elder_id) if a.date >= today]

    def update(self, appt_id: str, elder_id: str, date: str, label: str) -> Appointment:
        appt = Appointment(appt_id, elder_id, date, label)
        self._store.add(appt)
        return appt

    def remove(self, appt_id: str) -> None:
        self._store.remove(appt_id)
