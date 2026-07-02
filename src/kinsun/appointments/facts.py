"""回診事實提供者：把長輩即將到來的回診組成注入情境的一段文字。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

_PREFIX = "\n這位長者即將到來的回診（系統設定，僅供參考）：\n"


class AppointmentFacts:
    """facts(session_id) -> 注入文字。session_id 即長輩的 LINE user_id。"""

    def __init__(self, accounts, appointments, *, clock: Callable[[], datetime]) -> None:
        self._accounts = accounts
        self._appointments = appointments
        self._clock = clock

    def facts(self, session_id: str) -> str:
        elder = self._accounts.elder_by_line(session_id)
        if elder is None:
            return ""
        today = self._clock().date().isoformat()
        ups = self._appointments.upcoming(elder.elder_id, today)
        if not ups:
            return ""
        lines = "\n".join(f"- {a.date} {a.label}" for a in ups)
        return _PREFIX + lines + "\n"
