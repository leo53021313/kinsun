"""單元測試用的記憶體替身（不碰任何 DB／網路）。"""

from __future__ import annotations

from datetime import datetime

from kinsun.llm import Message


class FakeMemoryStore:
    def __init__(self) -> None:
        self._turns: dict[str, list[Message]] = {}
        self._last_user: dict[str, float] = {}
        self._clock = 0.0

    def append(self, session_id: str, message: Message) -> None:
        self._turns.setdefault(session_id, []).append(message)
        if message.role == "user":
            self._clock += 1.0
            self._last_user[session_id] = self._clock

    def recent(self, session_id: str) -> list[Message]:
        return list(self._turns.get(session_id, []))

    def sessions(self) -> list[str]:
        return sorted(self._turns)

    def last_active(self, session_id: str) -> float | None:
        return self._last_user.get(session_id)


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

    def save_elder(self, elder):
        self.elders[elder.elder_id] = elder

    def get_elder(self, elder_id):
        return self.elders.get(elder_id)

    def save_guardian(self, g):
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

    def save_elder_guardian(self, eg):
        self.elder_guardians[(eg.elder_id, eg.guardian_id)] = eg

    def get_elder_guardian(self, elder_id, guardian_id):
        return self.elder_guardians.get((elder_id, guardian_id))

    def list_elder_guardians(self, elder_id):
        rows = [v for (e, _), v in self.elder_guardians.items() if e == elder_id]
        return sorted(rows, key=lambda x: x.escalation_order)

    def elder_ids_of_guardian(self, guardian_id):
        return sorted(e for (e, g) in self.elder_guardians if g == guardian_id)

    def save_consent(self, c):
        self.consents[c.elder_id] = c

    def get_consent(self, elder_id):
        return self.consents.get(elder_id)

    def save_invite(self, i):
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
