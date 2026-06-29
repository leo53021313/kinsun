"""綁定引導流程的會話狀態：Protocol 與 Postgres 實作。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from kinsun.accounts.repository import AccountError
from kinsun.db import connect


class BindingState(StrEnum):
    MENU = "menu"
    AWAIT_ELDER_NAME = "elder_name"
    AWAIT_ELDER_PICK = "elder_pick"
    AWAIT_CODE = "code"
    AWAIT_CONFIRM = "confirm"
    MED_MENU = "med_menu"
    MED_PICK_ELDER = "med_pick_elder"
    MED_ADD_NAME = "med_add_name"
    MED_ADD_SLOTS = "med_add_slots"
    MED_DEL_PICK = "med_del_pick"


@dataclass(frozen=True)
class BindingSession:
    line_user_id: str
    state: BindingState
    data: dict
    updated_at: float


class BindingSessionStore(Protocol):
    def get(self, line_user_id: str) -> BindingSession | None: ...
    def save(self, session: BindingSession) -> None: ...
    def delete(self, line_user_id: str) -> None: ...


class PgBindingSessionStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def get(self, line_user_id: str) -> BindingSession | None:
        try:
            with connect(self._url) as conn:
                rows = conn.execute(
                    "SELECT line_user_id, state, data, updated_at "
                    "FROM binding_sessions WHERE line_user_id = %s",
                    (line_user_id,),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"讀取綁定會話失敗：{exc}") from exc
        if not rows:
            return None
        line, state, data, updated = rows[0]
        return BindingSession(line, BindingState(state), json.loads(data), updated)

    def save(self, session: BindingSession) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute(
                    "INSERT INTO binding_sessions (line_user_id, state, data, updated_at) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (line_user_id) DO UPDATE SET "
                    "state = EXCLUDED.state, data = EXCLUDED.data, "
                    "updated_at = EXCLUDED.updated_at",
                    (
                        session.line_user_id,
                        session.state.value,
                        json.dumps(session.data),
                        session.updated_at,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"寫入綁定會話失敗：{exc}") from exc

    def delete(self, line_user_id: str) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute(
                    "DELETE FROM binding_sessions WHERE line_user_id = %s", (line_user_id,)
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"刪除綁定會話失敗：{exc}") from exc
