"""帳號綁定生命週期。"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

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
from kinsun.accounts.repository import AccountRepository

CONSENT_VERSION = "1.0"


class InviteError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AccountService:
    def __init__(
        self,
        repo: AccountRepository,
        *,
        clock: Callable[[], datetime],
        new_id: Callable[[], str] | None = None,
        new_code: Callable[[], str] | None = None,
        ttl_hours: int = 24,
        max_attempts: int = 5,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._new_code = new_code or (lambda: secrets.token_urlsafe(12))
        self._ttl_hours = ttl_hours
        self._max_attempts = max_attempts

    def _guardian_for(self, line_user_id: str, name: str) -> Guardian:
        existing = self._repo.get_guardian_by_line(line_user_id)
        if existing is not None:
            return existing
        guardian = Guardian(self._new_id(), line_user_id, name)
        self._repo.save_guardian(guardian)
        return guardian

    def create_elder(self, guardian_line_id: str, guardian_name: str, elder_name: str) -> Elder:
        guardian = self._guardian_for(guardian_line_id, guardian_name)
        elder = Elder(self._new_id(), elder_name)
        self._repo.save_elder(elder)
        self._repo.save_elder_guardian(
            ElderGuardian(elder.elder_id, guardian.guardian_id, Role.PRIMARY, 1, True)
        )
        return elder

    def generate_invite(self, elder_id: str, role: InviteRole) -> Invite:
        expires_at = (self._clock() + timedelta(hours=self._ttl_hours)).timestamp()
        invite = Invite(self._new_code(), elder_id, role, expires_at, self._max_attempts)
        self._repo.save_invite(invite)
        return invite

    def redeem_invite(self, code: str, line_user_id: str, *, consent_by: ConsentBy) -> None:
        invite = self._repo.get_invite(code)
        if invite is None:
            raise InviteError("not_found")
        now = self._clock()
        if invite.used_at is not None:
            raise InviteError("used")
        if invite.attempts >= invite.max_attempts:
            self._fail(invite, "too_many_attempts")
        if now.timestamp() > invite.expires_at:
            self._fail(invite, "expired")

        if invite.role == InviteRole.ELDER:
            elder = self._repo.get_elder(invite.elder_id)
            if elder is None:
                raise InviteError("not_found")
            self._repo.save_elder(Elder(elder.elder_id, elder.name, line_user_id))
        else:
            guardian = self._guardian_for(line_user_id, "")
            order = max(
                (eg.escalation_order for eg in self._repo.list_elder_guardians(invite.elder_id)),
                default=0,
            )
            self._repo.save_elder_guardian(
                ElderGuardian(
                    invite.elder_id, guardian.guardian_id, Role.GUARDIAN, order + 1, False
                )
            )

        self._repo.save_consent(
            Consent(invite.elder_id, consent_by, CONSENT_VERSION, now.timestamp())
        )
        self._repo.save_invite(
            Invite(
                invite.code,
                invite.elder_id,
                invite.role,
                invite.expires_at,
                invite.max_attempts,
                invite.attempts + 1,
                now.timestamp(),
            )
        )

    def revoke_consent(self, elder_id: str) -> None:
        consent = self._repo.get_consent(elder_id)
        if consent is None:
            return
        self._repo.save_consent(
            Consent(
                consent.elder_id,
                consent.consent_by,
                consent.version,
                consent.granted_at,
                self._clock().timestamp(),
            )
        )

    def guardians_of(self, elder_id: str) -> list[ElderGuardian]:
        return self._repo.list_elder_guardians(elder_id)

    def guardian_line_ids(self, elder_line_id: str) -> list[str]:
        elder = self._repo.get_elder_by_line(elder_line_id)
        if elder is None:
            return []
        line_ids: list[str] = []
        for eg in self._repo.list_elder_guardians(elder.elder_id):
            guardian = self._repo.get_guardian(eg.guardian_id)
            if guardian is not None and guardian.line_user_id:
                line_ids.append(guardian.line_user_id)
        return line_ids

    def can_view_transcript(self, elder_id: str, guardian_id: str) -> bool:
        eg = self._repo.get_elder_guardian(elder_id, guardian_id)
        return eg is not None and eg.can_view_transcript

    def _fail(self, invite: Invite, reason: str) -> None:
        self._repo.save_invite(
            Invite(
                invite.code,
                invite.elder_id,
                invite.role,
                invite.expires_at,
                invite.max_attempts,
                invite.attempts + 1,
                invite.used_at,
            )
        )
        raise InviteError(reason)
