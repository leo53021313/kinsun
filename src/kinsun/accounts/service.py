"""帳號綁定生命週期。"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from kinsun.accounts.models import (
    ApiToken,
    Channel,
    ChannelBinding,
    Consent,
    GuardianAccount,
    ConsentBy,
    Elder,
    ElderGuardian,
    Guardian,
    Invite,
    InviteRole,
    PrincipalType,
    Role,
)
from kinsun.accounts.passwords import hash_password, verify_password
from kinsun.accounts.store import AccountStore

CONSENT_VERSION = "1.0"


class InviteError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AppAccountError(Exception):
    """App 帳號操作失敗：reason ∈ email_taken／invalid_credentials。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class InvitePreview:
    role: InviteRole
    elder_name: str
    reason: str | None


class AccountService:
    def __init__(
        self,
        repo: AccountStore,
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

    def _guardian_for(self, line_user_id: str, name: str, *, tx=None) -> Guardian:
        existing = self._repo.get_guardian_by_line(line_user_id)
        if existing is not None:
            return existing
        guardian = Guardian(self._new_id(), name)
        self._repo.save_guardian(guardian, tx=tx)
        self._repo.save_channel_binding(
            ChannelBinding(
                Channel.LINE,
                line_user_id,
                PrincipalType.GUARDIAN,
                guardian.guardian_id,
                self._clock().timestamp(),
            ),
            tx=tx,
        )
        return guardian

    def create_elder(self, guardian_line_id: str, guardian_name: str, elder_name: str) -> Elder:
        elder = Elder(self._new_id(), elder_name)
        with self._repo.transaction() as tx:
            guardian = self._guardian_for(guardian_line_id, guardian_name, tx=tx)
            self._repo.save_elder(elder, tx=tx)
            self._repo.save_elder_guardian(
                ElderGuardian(elder.elder_id, guardian.guardian_id, Role.PRIMARY, 1, True), tx=tx
            )
        return elder

    def generate_invite(self, elder_id: str, role: InviteRole) -> Invite:
        expires_at = (self._clock() + timedelta(hours=self._ttl_hours)).timestamp()
        invite = Invite(self._new_code(), elder_id, role, expires_at, self._max_attempts)
        self._repo.save_invite(invite)
        return invite

    def redeem_invite(
        self,
        code: str,
        external_id: str,
        *,
        channel: Channel = Channel.LINE,
        consent_by: ConsentBy,
    ) -> None:
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

        with self._repo.transaction() as tx:
            if invite.role == InviteRole.ELDER:
                elder = self._repo.get_elder(invite.elder_id)
                if elder is None:
                    raise InviteError("not_found")
                self._repo.save_channel_binding(
                    ChannelBinding(
                        channel,
                        external_id,
                        PrincipalType.ELDER,
                        elder.elder_id,
                        now.timestamp(),
                    ),
                    tx=tx,
                )
                self._repo.save_consent(
                    Consent(invite.elder_id, consent_by, CONSENT_VERSION, now.timestamp()), tx=tx
                )
            else:
                guardian = self._guardian_for(external_id, "", tx=tx)
                egs = self._repo.list_elder_guardians(invite.elder_id)
                order = max((eg.escalation_order for eg in egs), default=0)
                self._repo.save_elder_guardian(
                    ElderGuardian(
                        invite.elder_id, guardian.guardian_id, Role.GUARDIAN, order + 1, False
                    ),
                    tx=tx,
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
                ),
                tx=tx,
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

    def has_valid_consent(self, elder_id: str) -> bool:
        """長輩同意是否有效（存在且未撤回）。"""
        consent = self._repo.get_consent(elder_id)
        return consent is not None and consent.revoked_at is None

    def _issue_token(self, principal_type: PrincipalType, principal_id: str, *, tx=None) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._repo.save_api_token(
            ApiToken(token_hash, principal_type, principal_id, self._clock().timestamp()), tx=tx
        )
        return token

    def register_guardian_account(
        self, email: str, password: str, name: str
    ) -> tuple[Guardian, str]:
        """家屬註冊：建 Guardian＋登入帳號並發 token。email 重複丟 email_taken。"""
        normalized = email.strip().lower()
        if self._repo.get_guardian_account_by_email(normalized) is not None:
            raise AppAccountError("email_taken")
        guardian = Guardian(self._new_id(), name)
        with self._repo.transaction() as tx:
            self._repo.save_guardian(guardian, tx=tx)
            self._repo.save_guardian_account(
                GuardianAccount(
                    guardian.guardian_id,
                    normalized,
                    hash_password(password),
                    self._clock().timestamp(),
                ),
                tx=tx,
            )
            token = self._issue_token(PrincipalType.GUARDIAN, guardian.guardian_id, tx=tx)
        return guardian, token

    def login_guardian(self, email: str, password: str) -> tuple[Guardian, str]:
        """家屬登入：查無帳號或密碼錯一律 invalid_credentials（不洩漏帳號存在性）。"""
        account = self._repo.get_guardian_account_by_email(email.strip().lower())
        if account is None or not verify_password(password, account.password_hash):
            raise AppAccountError("invalid_credentials")
        guardian = self._repo.get_guardian(account.guardian_id)
        if guardian is None:
            raise AppAccountError("invalid_credentials")
        return guardian, self._issue_token(PrincipalType.GUARDIAN, guardian.guardian_id)

    def bind_elder_device(self, code: str, *, consent_by: ConsentBy) -> tuple[Elder, str]:
        """長輩裝置綁定：綁定碼換 App 通道綁定＋裝置 token。InviteError 原樣上拋。"""
        invite = self._repo.get_invite(code)
        app_account_id = self._new_id()
        self.redeem_invite(code, app_account_id, channel=Channel.APP, consent_by=consent_by)
        elder = self._repo.get_elder(invite.elder_id)  # redeem 成功即存在
        return elder, self._issue_token(PrincipalType.ELDER, elder.elder_id)

    def authenticate_token(self, token: str) -> ApiToken | None:
        return self._repo.get_api_token(hashlib.sha256(token.encode()).hexdigest())

    def consented_elder_id(self, channel: Channel, external_id: str) -> str | None:
        """解析「已同意的長輩」：該通道帳號綁的是長輩且同意有效才回 elder_id，否則 None。"""
        binding = self._repo.get_channel_binding(channel, external_id)
        if binding is None or binding.principal_type is not PrincipalType.ELDER:
            return None
        return binding.principal_id if self.has_valid_consent(binding.principal_id) else None

    def get_elder(self, elder_id: str):
        return self._repo.get_elder(elder_id)

    def preview_invite(self, code: str) -> InvitePreview | None:
        invite = self._repo.get_invite(code)
        if invite is None:
            return None
        elder = self._repo.get_elder(invite.elder_id)
        elder_name = elder.name if elder is not None else ""
        reason: str | None = None
        if invite.used_at is not None:
            reason = "used"
        elif invite.attempts >= invite.max_attempts:
            reason = "too_many_attempts"
        elif self._clock().timestamp() > invite.expires_at:
            reason = "expired"
        return InvitePreview(invite.role, elder_name, reason)

    def elders_managed_by(self, line_user_id: str) -> list[Elder]:
        guardian = self._repo.get_guardian_by_line(line_user_id)
        if guardian is None:
            return []
        elders: list[Elder] = []
        for elder_id in self._repo.elder_ids_of_guardian(guardian.guardian_id):
            elder = self._repo.get_elder(elder_id)
            if elder is not None:
                elders.append(elder)
        return elders

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
