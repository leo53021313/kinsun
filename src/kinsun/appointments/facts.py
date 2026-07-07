"""回診事實提供者：把長輩即將到來的回診組成注入情境的一段（FactSection）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.memory.models import FactSection

_TITLE = "\n這位長者即將到來的回診（系統設定，僅供參考）：\n"


class AppointmentFacts:
    """facts(elder_id) -> FactSection | None（無回診回 None）。"""

    def __init__(self, appointments, *, clock: Callable[[], datetime]) -> None:
        self._appointments = appointments
        self._clock = clock

    def facts(self, elder_id: str) -> FactSection | None:
        today = self._clock().date().isoformat()
        ups = self._appointments.upcoming(elder_id, today)
        if not ups:
            return None
        return FactSection(_TITLE, [f"{a.date} {a.label}" for a in ups])
