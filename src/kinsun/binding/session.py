"""綁定引導流程的會話狀態：Protocol 與 Postgres 實作。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from kinsun.db import Database, _Errors


class BindingState(StrEnum):
    MENU = "menu"
    AWAIT_ELDER_NAME = "elder_name"
    AWAIT_ELDER_PICK = "elder_pick"
    AWAIT_CODE = "code"
    AWAIT_CONFIRM = "confirm"
    # 提醒設定（D-76 P3 入口合一）：用藥、回診與其他提醒共用同一組狀態。
    SCHED_MENU = "sched_menu"
    SCHED_PICK_ELDER = "sched_pick_elder"
    SCHED_ADD_KIND = "sched_add_kind"
    SCHED_ADD_TITLE = "sched_add_title"
    SCHED_ADD_WHEN = "sched_add_when"
    SCHED_DEL_PICK = "sched_del_pick"


@dataclass(frozen=True)
class BindingSession:
    line_user_id: str
    state: BindingState
    data: dict
    updated_at: float


class BindingSessionError(Exception):
    """綁定會話讀寫失敗。"""


class BindingSessionStore(Protocol):
    def get(self, line_user_id: str) -> BindingSession | None: ...
    def save(self, session: BindingSession) -> None: ...
    def delete(self, line_user_id: str) -> None: ...


class PgBindingSessionStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: BindingSessionError(f"綁定會話存取失敗：{m}"))

    def get(self, line_user_id: str) -> BindingSession | None:
        rows = self._db.query(
            "SELECT line_user_id, state, data, updated_at "
            "FROM binding_sessions WHERE line_user_id = %s",
            (line_user_id,),
        )
        if not rows:
            return None
        line_user_id, state, data, updated = rows[0]
        return BindingSession(line_user_id, BindingState(state), json.loads(data), updated)

    def save(self, session: BindingSession) -> None:
        self._db.execute(
            "INSERT INTO binding_sessions (line_user_id, state, data, updated_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (line_user_id) DO UPDATE SET "
            "state = EXCLUDED.state, data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
            (
                session.line_user_id,
                session.state.value,
                json.dumps(session.data),
                session.updated_at,
            ),
        )

    def delete(self, line_user_id: str) -> None:
        self._db.execute("DELETE FROM binding_sessions WHERE line_user_id = %s", (line_user_id,))


class FakeBindingSessionStore:
    """BindingSessionStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, BindingSession] = {}

    def get(self, line_user_id: str) -> BindingSession | None:
        return self._sessions.get(line_user_id)

    def save(self, session: BindingSession) -> None:
        self._sessions[session.line_user_id] = session

    def delete(self, line_user_id: str) -> None:
        self._sessions.pop(line_user_id, None)
