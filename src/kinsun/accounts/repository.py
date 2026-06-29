"""帳號綁定的儲存層：Protocol 與 Postgres（Supabase）實作。"""

from __future__ import annotations

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
from kinsun.db import connect


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


class PgAccountRepository:
    """帳號綁定的 Postgres（Supabase）實作；介面同 AccountRepository。"""

    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _exec(self, sql: str, params: tuple) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute(sql, params)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"寫入失敗：{exc}") from exc

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        try:
            with connect(self._url) as conn:
                return conn.execute(sql, params).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise AccountError(f"讀取失敗：{exc}") from exc

    def save_elder(self, elder: Elder) -> None:
        self._exec(
            "INSERT INTO elders (elder_id, name, line_user_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (elder_id) DO UPDATE SET "
            "name = EXCLUDED.name, line_user_id = EXCLUDED.line_user_id",
            (elder.elder_id, elder.name, elder.line_user_id),
        )

    def get_elder(self, elder_id: str) -> Elder | None:
        rows = self._query(
            "SELECT elder_id, name, line_user_id FROM elders WHERE elder_id = %s", (elder_id,)
        )
        return Elder(*rows[0]) if rows else None

    def save_guardian(self, guardian: Guardian) -> None:
        self._exec(
            "INSERT INTO guardians (guardian_id, line_user_id, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (guardian_id) DO UPDATE SET "
            "line_user_id = EXCLUDED.line_user_id, name = EXCLUDED.name",
            (guardian.guardian_id, guardian.line_user_id, guardian.name),
        )

    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None:
        rows = self._query(
            "SELECT guardian_id, line_user_id, name FROM guardians WHERE line_user_id = %s",
            (line_user_id,),
        )
        return Guardian(*rows[0]) if rows else None

    def save_elder_guardian(self, eg: ElderGuardian) -> None:
        self._exec(
            "INSERT INTO elder_guardians "
            "(elder_id, guardian_id, role, escalation_order, can_view_transcript) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (elder_id, guardian_id) DO UPDATE SET "
            "role = EXCLUDED.role, escalation_order = EXCLUDED.escalation_order, "
            "can_view_transcript = EXCLUDED.can_view_transcript",
            (
                eg.elder_id,
                eg.guardian_id,
                eg.role.value,
                eg.escalation_order,
                bool(eg.can_view_transcript),
            ),
        )

    def _to_eg(self, row: tuple) -> ElderGuardian:
        elder_id, guardian_id, role, order, can_view = row
        return ElderGuardian(elder_id, guardian_id, Role(role), order, bool(can_view))

    def get_elder_guardian(self, elder_id: str, guardian_id: str) -> ElderGuardian | None:
        rows = self._query(
            "SELECT elder_id, guardian_id, role, escalation_order, can_view_transcript "
            "FROM elder_guardians WHERE elder_id = %s AND guardian_id = %s",
            (elder_id, guardian_id),
        )
        return self._to_eg(rows[0]) if rows else None

    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]:
        rows = self._query(
            "SELECT elder_id, guardian_id, role, escalation_order, can_view_transcript "
            "FROM elder_guardians WHERE elder_id = %s ORDER BY escalation_order",
            (elder_id,),
        )
        return [self._to_eg(r) for r in rows]

    def save_consent(self, consent: Consent) -> None:
        self._exec(
            "INSERT INTO consents (elder_id, consent_by, version, granted_at, revoked_at) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (elder_id) DO UPDATE SET "
            "consent_by = EXCLUDED.consent_by, version = EXCLUDED.version, "
            "granted_at = EXCLUDED.granted_at, revoked_at = EXCLUDED.revoked_at",
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
            "FROM consents WHERE elder_id = %s",
            (elder_id,),
        )
        if not rows:
            return None
        elder, by, version, granted, revoked = rows[0]
        return Consent(elder, ConsentBy(by), version, granted, revoked)

    def save_invite(self, invite: Invite) -> None:
        self._exec(
            "INSERT INTO invites "
            "(code, elder_id, role, expires_at, max_attempts, attempts, used_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (code) DO UPDATE SET "
            "elder_id = EXCLUDED.elder_id, role = EXCLUDED.role, "
            "expires_at = EXCLUDED.expires_at, max_attempts = EXCLUDED.max_attempts, "
            "attempts = EXCLUDED.attempts, used_at = EXCLUDED.used_at",
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
            "FROM invites WHERE code = %s",
            (code,),
        )
        if not rows:
            return None
        c, elder, role, expires, max_a, attempts, used = rows[0]
        return Invite(c, elder, InviteRole(role), expires, max_a, attempts, used)
