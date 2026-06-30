"""單元測試用的記憶體替身（不碰任何 DB／網路）。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from kinsun.llm import Message
from kinsun.memory.store import previous_day_bounds
from kinsun.safety.events import RiskEvent

_TPE = timezone(timedelta(hours=8))
_DEFAULT_NOW = datetime(2026, 6, 29, 3, 0, tzinfo=_TPE)


class FakeMemoryStore:
    """以時間戳記錄每輪對話，可模擬「今天」與「前一天」的日界查詢。"""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or _DEFAULT_NOW
        self._turns: dict[str, list[tuple[float, Message]]] = {}

    def append(self, session_id: str, message: Message, *, at: datetime | None = None) -> None:
        ts = (at or self._now).timestamp()
        self._turns.setdefault(session_id, []).append((ts, message))

    def recent(self, session_id: str) -> list[Message]:
        midnight = self._now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return [m for ts, m in self._turns.get(session_id, []) if ts >= midnight]

    def previous_day(self, session_id: str) -> list[Message]:
        start, end = previous_day_bounds(self._now)
        return [m for ts, m in self._turns.get(session_id, []) if start <= ts < end]

    def sessions(self) -> list[str]:
        return sorted(self._turns)

    def last_active(self, session_id: str) -> float | None:
        users = [ts for ts, m in self._turns.get(session_id, []) if m.role == "user"]
        return max(users) if users else None


class FakeLongTermStore:
    def __init__(self, search_result: str = "") -> None:
        self.added: list[tuple[str, list[Message], str]] = []
        self._search_result = search_result

    def add(
        self, session_id: str, messages: list[Message], *, provenance: str = "self_claimed"
    ) -> None:
        self.added.append((session_id, list(messages), provenance))

    def search(self, session_id: str, query: str, *, top_k: int = 5) -> str:
        return self._search_result


class FakeAccountRepository:
    def __init__(self) -> None:
        self.elders = {}
        self.guardians = {}
        self.guardians_by_line = {}
        self.elder_guardians = {}
        self.consents = {}
        self.invites = {}

    @contextmanager
    def transaction(self):
        yield None

    def save_elder(self, elder, *, tx=None):
        self.elders[elder.elder_id] = elder

    def get_elder(self, elder_id):
        return self.elders.get(elder_id)

    def save_guardian(self, g, *, tx=None):
        self.guardians[g.guardian_id] = g
        self.guardians_by_line[g.line_user_id] = g

    def get_guardian_by_line(self, line_user_id):
        return self.guardians_by_line.get(line_user_id)

    def get_elder_by_line(self, line_user_id):
        for elder in self.elders.values():
            if elder.line_user_id == line_user_id:
                return elder
        return None

    def get_guardian(self, guardian_id):
        return self.guardians.get(guardian_id)

    def save_elder_guardian(self, eg, *, tx=None):
        self.elder_guardians[(eg.elder_id, eg.guardian_id)] = eg

    def get_elder_guardian(self, elder_id, guardian_id):
        return self.elder_guardians.get((elder_id, guardian_id))

    def list_elder_guardians(self, elder_id):
        rows = [v for (e, _), v in self.elder_guardians.items() if e == elder_id]
        return sorted(rows, key=lambda x: x.escalation_order)

    def elder_ids_of_guardian(self, guardian_id):
        return sorted(e for (e, g) in self.elder_guardians if g == guardian_id)

    def save_consent(self, c, *, tx=None):
        self.consents[c.elder_id] = c

    def get_consent(self, elder_id):
        return self.consents.get(elder_id)

    def save_invite(self, i, *, tx=None):
        self.invites[i.code] = i

    def get_invite(self, code):
        return self.invites.get(code)


class FakeBindingSessionStore:
    def __init__(self) -> None:
        self._sessions = {}

    def get(self, line_user_id):
        return self._sessions.get(line_user_id)

    def save(self, session):
        self._sessions[session.line_user_id] = session

    def delete(self, line_user_id):
        self._sessions.pop(line_user_id, None)


class FakeScheduleStateStore:
    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def get_last_run(self, job_name: str) -> datetime | None:
        return self._last.get(job_name)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._last[job_name] = when


class FakeMedicationStore:
    def __init__(self) -> None:
        self._meds = {}

    def add(self, med):
        self._meds[med.med_id] = med

    def list_for_elder(self, elder_id):
        rows = [m for m in self._meds.values() if m.elder_id == elder_id]
        return sorted(rows, key=lambda m: m.name)

    def list_for_slot(self, slot):
        return [m for m in self._meds.values() if slot in m.slots]

    def remove(self, med_id):
        self._meds.pop(med_id, None)


class FakeAppointmentStore:
    def __init__(self) -> None:
        self._appts = {}

    def add(self, appt):
        self._appts[appt.appt_id] = appt

    def list_for_elder(self, elder_id):
        rows = [a for a in self._appts.values() if a.elder_id == elder_id]
        return sorted(rows, key=lambda a: a.date)

    def list_for_date(self, date):
        return [a for a in self._appts.values() if a.date == date]

    def remove(self, appt_id):
        self._appts.pop(appt_id, None)


class FakeRiskEventStore:
    def __init__(self) -> None:
        self.recorded: list[tuple] = []

    def record(self, session_id, assessment):
        self.recorded.append((session_id, assessment))

    def list_for_session(self, session_id):
        return [
            RiskEvent(str(i), s, a.tier, a.reason, float(i))
            for i, (s, a) in enumerate(self.recorded)
            if s == session_id
        ]
