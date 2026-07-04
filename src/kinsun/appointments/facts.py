"""回診事實提供者：把長輩即將到來的回診組成注入情境的一段（FactSection）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.memory.models import FactSection

_TITLE = "\n這位長者即將到來的回診（系統設定，僅供參考）：\n"


class AppointmentFacts:
    """facts(line_user_id) -> FactSection | None（無綁定或無回診回 None）。"""

    def __init__(self, accounts, appointments, *, clock: Callable[[], datetime]) -> None:
        self._accounts = accounts
        self._appointments = appointments
        self._clock = clock

    def facts(self, line_user_id: str) -> FactSection | None:
        elder = self._accounts.elder_by_line(line_user_id)
        if elder is None:
            return None
        today = self._clock().date().isoformat()
        ups = self._appointments.upcoming(elder.elder_id, today)
        if not ups:
            return None
        return FactSection(_TITLE, [f"{a.date} {a.label}" for a in ups])
