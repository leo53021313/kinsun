"""帳號綁定的 SQLite 儲存。"""

from __future__ import annotations

import sqlite3
from typing import Protocol

from kinsun.accounts.models import (
    Consent,
    ConsentBy,
    Elder,
    ElderGuardian,
    Guardian,
    Invite,
    InviteRole,
    Role,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS elders (
    elder_id TEXT PRIMARY KEY, name TEXT NOT NULL, line_user_id TEXT);
CREATE TABLE IF NOT EXISTS guardians (
    guardian_id TEXT PRIMARY KEY, line_user_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS elder_guardians (
    elder_id TEXT NOT NULL, guardian_id TEXT NOT NULL, role TEXT NOT NULL,
    escalation_order INTEGER NOT NULL, can_view_transcript INTEGER NOT NULL,
    PRIMARY KEY (elder_id, guardian_id));
CREATE TABLE IF NOT EXISTS consents (
    elder_id TEXT PRIMARY KEY, consent_by TEXT NOT NULL, version TEXT NOT NULL,
    granted_at REAL NOT NULL, revoked_at REAL);
CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY, elder_id TEXT NOT NULL, role TEXT NOT NULL,
    expires_at REAL NOT NULL, max_attempts INTEGER NOT NULL,
    attempts INTEGER NOT NULL, used_at REAL);
"""


class AccountError(Exception):
    """帳號資料讀寫失敗。"""


class AccountRepository(Protocol):
    def save_elder(self, elder: Elder) -> None: ...
    def get_elder(self, elder_id: str) -> Elder | None: ...
    def save_guardian(self, guardian: Guardian) -> None: ...
    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None: ...
    def save_elder_guardian(self, eg: ElderGuardian) -> None: ...
    def get_elder_guardian(self, elder_id: str, guardian_id: str) -> ElderGuardian | None: ...
    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]: ...
    def save_consent(self, consent: Consent) -> None: ...
    def get_consent(self, elder_id: str) -> Consent | None: ...
    def save_invite(self, invite: Invite) -> None: ...
    def get_invite(self, code: str) -> Invite | None: ...


class SqliteAccountRepository:
    def __init__(self, db_path: str) -> None:
        try:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise AccountError(f"無法開啟帳號資料庫：{exc}") from exc

    def _exec(self, sql: str, params: tuple) -> None:
        try:
            self._conn.execute(sql, params)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise AccountError(f"寫入失敗：{exc}") from exc

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        try:
            return self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise AccountError(f"讀取失敗：{exc}") from exc

    def save_elder(self, elder: Elder) -> None:
        self._exec(
            "INSERT OR REPLACE INTO elders (elder_id, name, line_user_id) VALUES (?, ?, ?)",
            (elder.elder_id, elder.name, elder.line_user_id),
        )

    def get_elder(self, elder_id: str) -> Elder | None:
        rows = self._query(
            "SELECT elder_id, name, line_user_id FROM elders WHERE elder_id = ?", (elder_id,)
        )
        return Elder(*rows[0]) if rows else None

    def save_guardian(self, guardian: Guardian) -> None:
        self._exec(
            "INSERT OR REPLACE INTO guardians (guardian_id, line_user_id, name) VALUES (?, ?, ?)",
            (guardian.guardian_id, guardian.line_user_id, guardian.name),
        )

    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None:
        rows = self._query(
            "SELECT guardian_id, line_user_id, name FROM guardians WHERE line_user_id = ?",
            (line_user_id,),
        )
        return Guardian(*rows[0]) if rows else None

    def save_elder_guardian(self, eg: ElderGuardian) -> None:
        self._exec(
            "INSERT OR REPLACE INTO elder_guardians "
            "(elder_id, guardian_id, role, escalation_order, can_view_transcript) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                eg.elder_id,
                eg.guardian_id,
                eg.role.value,
                eg.escalation_order,
                int(eg.can_view_transcript),
            ),
        )

    def _to_eg(self, row: tuple) -> ElderGuardian:
        elder_id, guardian_id, role, order, can_view = row
        return ElderGuardian(elder_id, guardian_id, Role(role), order, bool(can_view))

    def get_elder_guardian(self, elder_id: str, guardian_id: str) -> ElderGuardian | None:
        rows = self._query(
            "SELECT elder_id, guardian_id, role, escalation_order, can_view_transcript "
            "FROM elder_guardians WHERE elder_id = ? AND guardian_id = ?",
            (elder_id, guardian_id),
        )
        return self._to_eg(rows[0]) if rows else None

    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]:
        rows = self._query(
            "SELECT elder_id, guardian_id, role, escalation_order, can_view_transcript "
            "FROM elder_guardians WHERE elder_id = ? ORDER BY escalation_order",
            (elder_id,),
        )
        return [self._to_eg(row) for row in rows]

    def save_consent(self, consent: Consent) -> None:
        self._exec(
            "INSERT OR REPLACE INTO consents "
            "(elder_id, consent_by, version, granted_at, revoked_at) VALUES (?, ?, ?, ?, ?)",
            (
                consent.elder_id,
                consent.consent_by.value,
                consent.version,
                consent.granted_at,
                consent.revoked_at,
            ),
        )

    def get_consent(self, elder_id: str) -> Consent | None:
        rows = self._query(
            "SELECT elder_id, consent_by, version, granted_at, revoked_at "
            "FROM consents WHERE elder_id = ?",
            (elder_id,),
        )
        if not rows:
            return None
        elder, by, version, granted, revoked = rows[0]
        return Consent(elder, ConsentBy(by), version, granted, revoked)

    def save_invite(self, invite: Invite) -> None:
        self._exec(
            "INSERT OR REPLACE INTO invites "
            "(code, elder_id, role, expires_at, max_attempts, attempts, used_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                invite.code,
                invite.elder_id,
                invite.role.value,
                invite.expires_at,
                invite.max_attempts,
                invite.attempts,
                invite.used_at,
            ),
        )

    def get_invite(self, code: str) -> Invite | None:
        rows = self._query(
            "SELECT code, elder_id, role, expires_at, max_attempts, attempts, used_at "
            "FROM invites WHERE code = ?",
            (code,),
        )
        if not rows:
            return None
        c, elder, role, expires, max_a, attempts, used = rows[0]
        return Invite(c, elder, InviteRole(role), expires, max_a, attempts, used)
