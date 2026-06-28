"""帳號綁定生命週期。"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from kinsun.accounts.models import (
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
