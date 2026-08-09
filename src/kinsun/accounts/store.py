"""帳號綁定的儲存層：Protocol 與 Postgres（Supabase）實作。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from kinsun.accounts.models import (
    ApiToken,
    Channel,
    ChannelBinding,
    Consent,
    ConsentBy,
    Elder,
    ElderAccount,
    ElderGuardian,
    Guardian,
    GuardianAccount,
    Invite,
    InviteRole,
    PrincipalType,
    Role,
)
from kinsun.db import Database, Executor, _Errors


class AccountError(Exception):
    """帳號資料讀寫失敗。"""


class AccountStore(Protocol):
    def save_elder(self, elder: Elder, *, tx: Executor | None = None) -> None: ...
    def get_elder(self, elder_id: str) -> Elder | None: ...
    def save_guardian(self, guardian: Guardian, *, tx: Executor | None = None) -> None: ...
    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None: ...
    def get_guardian(self, guardian_id: str) -> Guardian | None: ...
    def get_elder_by_line(self, line_user_id: str) -> Elder | None: ...
    def save_elder_guardian(self, eg: ElderGuardian, *, tx: Executor | None = None) -> None: ...
    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]: ...
    def elder_ids_of_guardian(self, guardian_id: str) -> list[str]: ...
    def save_consent(self, consent: Consent, *, tx: Executor | None = None) -> None: ...
    def get_consent(self, elder_id: str) -> Consent | None: ...
    def save_invite(self, invite: Invite, *, tx: Executor | None = None) -> None: ...
    def get_invite(
        self, code: str, *, tx: Executor | None = None, for_update: bool = False
    ) -> Invite | None: ...
    def list_invites_for_elder(self, elder_id: str) -> list[Invite]: ...
    def save_channel_binding(
        self, binding: ChannelBinding, *, tx: Executor | None = None
    ) -> None: ...
    def get_channel_binding(self, channel: Channel, external_id: str) -> ChannelBinding | None: ...
    def list_channel_bindings_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ChannelBinding]: ...
    def save_guardian_account(
        self, account: GuardianAccount, *, tx: Executor | None = None
    ) -> None: ...
    def get_guardian_account_by_email(self, email: str) -> GuardianAccount | None: ...
    def save_elder_account(self, account: ElderAccount, *, tx: Executor | None = None) -> None: ...
    def get_elder_account_by_phone(self, phone: str) -> ElderAccount | None: ...
    def get_elder_account(self, elder_id: str) -> ElderAccount | None: ...
    def save_api_token(self, token: ApiToken, *, tx: Executor | None = None) -> None: ...
    def get_api_token(self, token_hash: str) -> ApiToken | None: ...
    def list_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ApiToken]: ...
    def remove_api_token(self, token_hash: str) -> None: ...
    def remove_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str, *, tx: Executor | None = None
    ) -> None: ...
    def remove_channel_bindings_for_principal(
        self,
        channel: Channel,
        principal_type: PrincipalType,
        principal_id: str,
        *,
        tx: Executor | None = None,
    ) -> None: ...
    def transaction(self) -> object: ...


class PgAccountStore:
    """帳號綁定的 Postgres（Supabase）實作；介面同 AccountStore。"""

    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: AccountError(f"帳號存取失敗：{m}"))

    @contextmanager
    def transaction(self) -> Iterator[Executor]:
        with self._db.transaction() as tx:
            yield tx

    def save_elder(self, elder: Elder, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO elders (elder_id, name, nickname, persona) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (elder_id) DO UPDATE SET "
            "name = EXCLUDED.name, nickname = EXCLUDED.nickname, persona = EXCLUDED.persona",
            (elder.elder_id, elder.name, elder.nickname, elder.persona),
        )

    def get_elder(self, elder_id: str) -> Elder | None:
        rows = self._db.query(
            "SELECT elder_id, name, nickname, persona FROM elders WHERE elder_id = %s",
            (elder_id,),
        )
        return Elder(*rows[0]) if rows else None

    def save_guardian(self, guardian: Guardian, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO guardians (guardian_id, name) VALUES (%s, %s) "
            "ON CONFLICT (guardian_id) DO UPDATE SET name = EXCLUDED.name",
            (guardian.guardian_id, guardian.name),
        )

    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None:
        # 讀取端經 channel_bindings（1C）；guardians.line_user_id 欄位已於 1D 退役 DROP。
        binding = self.get_channel_binding(Channel.LINE, line_user_id)
        if binding is None or binding.principal_type is not PrincipalType.GUARDIAN:
            return None
        return self.get_guardian(binding.principal_id)

    def get_guardian(self, guardian_id: str) -> Guardian | None:
        rows = self._db.query(
            "SELECT guardian_id, name FROM guardians WHERE guardian_id = %s", (guardian_id,)
        )
        return Guardian(*rows[0]) if rows else None

    def get_elder_by_line(self, line_user_id: str) -> Elder | None:
        # 讀取端經 channel_bindings（1C）；elders.line_user_id 欄位已於 1D 退役 DROP。
        binding = self.get_channel_binding(Channel.LINE, line_user_id)
        if binding is None or binding.principal_type is not PrincipalType.ELDER:
            return None
        return self.get_elder(binding.principal_id)

    def save_elder_guardian(self, eg: ElderGuardian, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO elder_guardians "
            "(elder_id, guardian_id, role, escalation_order) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (elder_id, guardian_id) DO UPDATE SET "
            "role = EXCLUDED.role, escalation_order = EXCLUDED.escalation_order",
            (
                eg.elder_id,
                eg.guardian_id,
                eg.role.value,
                eg.escalation_order,
            ),
        )

    def _to_eg(self, row: tuple) -> ElderGuardian:
        elder_id, guardian_id, role, order = row
        return ElderGuardian(elder_id, guardian_id, Role(role), order)

    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]:
        rows = self._db.query(
            "SELECT elder_id, guardian_id, role, escalation_order "
            "FROM elder_guardians WHERE elder_id = %s ORDER BY escalation_order",
            (elder_id,),
        )
        return [self._to_eg(r) for r in rows]

    def elder_ids_of_guardian(self, guardian_id: str) -> list[str]:
        rows = self._db.query(
            "SELECT elder_id FROM elder_guardians WHERE guardian_id = %s ORDER BY elder_id",
            (guardian_id,),
        )
        return [r[0] for r in rows]

    def save_consent(self, consent: Consent, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
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
        rows = self._db.query(
            "SELECT elder_id, consent_by, version, granted_at, revoked_at "
            "FROM consents WHERE elder_id = %s",
            (elder_id,),
        )
        if not rows:
            return None
        elder, by, version, granted, revoked = rows[0]
        return Consent(elder, ConsentBy(by), version, granted, revoked)

    def save_invite(self, invite: Invite, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
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

    def get_invite(
        self, code: str, *, tx: Executor | None = None, for_update: bool = False
    ) -> Invite | None:
        """for_update（✅ 庚-19）：交易內列鎖住該碼——並發同碼 redeem 的第二個
        請求在此等待首個 commit，之後看到 used_at 被正確擋下（根治 TOCTOU）。"""
        sql = (
            "SELECT code, elder_id, role, expires_at, max_attempts, attempts, used_at "
            "FROM invites WHERE code = %s"
        )
        if for_update:
            sql += " FOR UPDATE"
        rows = (tx or self._db).query(sql, (code,))
        if not rows:
            return None
        c, elder, role, expires, max_a, attempts, used = rows[0]
        return Invite(c, elder, InviteRole(role), expires, max_a, attempts, used)

    def list_invites_for_elder(self, elder_id: str) -> list[Invite]:
        rows = self._db.query(
            "SELECT code, elder_id, role, expires_at, max_attempts, attempts, used_at "
            "FROM invites WHERE elder_id = %s ORDER BY expires_at DESC",
            (elder_id,),
        )
        return [Invite(c, e, InviteRole(r), exp, m, a, u) for (c, e, r, exp, m, a, u) in rows]

    def save_channel_binding(self, binding: ChannelBinding, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO channel_bindings "
            "(channel, external_id, principal_type, principal_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (channel, external_id) DO UPDATE SET "
            "principal_type = EXCLUDED.principal_type, principal_id = EXCLUDED.principal_id",
            (
                binding.channel.value,
                binding.external_id,
                binding.principal_type.value,
                binding.principal_id,
                binding.created_at,
            ),
        )

    def get_channel_binding(self, channel: Channel, external_id: str) -> ChannelBinding | None:
        rows = self._db.query(
            "SELECT channel, external_id, principal_type, principal_id, created_at "
            "FROM channel_bindings WHERE channel = %s AND external_id = %s",
            (channel.value, external_id),
        )
        if not rows:
            return None
        ch, ext, ptype, pid, created = rows[0]
        return ChannelBinding(Channel(ch), ext, PrincipalType(ptype), pid, created)

    def list_channel_bindings_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ChannelBinding]:
        rows = self._db.query(
            "SELECT channel, external_id, principal_type, principal_id, created_at "
            "FROM channel_bindings WHERE principal_type = %s AND principal_id = %s "
            "ORDER BY channel, external_id",
            (principal_type.value, principal_id),
        )
        return [ChannelBinding(Channel(c), e, PrincipalType(p), i, t) for (c, e, p, i, t) in rows]

    def save_guardian_account(
        self, account: GuardianAccount, *, tx: Executor | None = None
    ) -> None:
        (tx or self._db).execute(
            "INSERT INTO guardian_accounts (guardian_id, email, password_hash, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (guardian_id) DO UPDATE SET "
            "email = EXCLUDED.email, password_hash = EXCLUDED.password_hash",
            (account.guardian_id, account.email, account.password_hash, account.created_at),
        )

    def get_guardian_account_by_email(self, email: str) -> GuardianAccount | None:
        rows = self._db.query(
            "SELECT guardian_id, email, password_hash, created_at "
            "FROM guardian_accounts WHERE email = %s",
            (email,),
        )
        return GuardianAccount(*rows[0]) if rows else None

    def save_elder_account(self, account: ElderAccount, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO elder_accounts (elder_id, phone, password_hash, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (elder_id) DO UPDATE SET "
            "phone = EXCLUDED.phone, password_hash = EXCLUDED.password_hash",
            (account.elder_id, account.phone, account.password_hash, account.created_at),
        )

    def get_elder_account_by_phone(self, phone: str) -> ElderAccount | None:
        rows = self._db.query(
            "SELECT elder_id, phone, password_hash, created_at "
            "FROM elder_accounts WHERE phone = %s",
            (phone,),
        )
        return ElderAccount(*rows[0]) if rows else None

    def get_elder_account(self, elder_id: str) -> ElderAccount | None:
        rows = self._db.query(
            "SELECT elder_id, phone, password_hash, created_at "
            "FROM elder_accounts WHERE elder_id = %s",
            (elder_id,),
        )
        return ElderAccount(*rows[0]) if rows else None

    def save_api_token(self, token: ApiToken, *, tx: Executor | None = None) -> None:
        (tx or self._db).execute(
            "INSERT INTO api_tokens (token_hash, principal_type, principal_id, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (token_hash) DO NOTHING",
            (token.token_hash, token.principal_type.value, token.principal_id, token.created_at),
        )

    def get_api_token(self, token_hash: str) -> ApiToken | None:
        rows = self._db.query(
            "SELECT token_hash, principal_type, principal_id, created_at "
            "FROM api_tokens WHERE token_hash = %s",
            (token_hash,),
        )
        if not rows:
            return None
        h, ptype, pid, created = rows[0]
        return ApiToken(h, PrincipalType(ptype), pid, created)

    def list_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ApiToken]:
        rows = self._db.query(
            "SELECT token_hash, principal_type, principal_id, created_at FROM api_tokens "
            "WHERE principal_type = %s AND principal_id = %s ORDER BY created_at DESC",
            (principal_type.value, principal_id),
        )
        return [ApiToken(h, PrincipalType(p), i, c) for (h, p, i, c) in rows]

    def remove_api_token(self, token_hash: str) -> None:
        self._db.execute("DELETE FROM api_tokens WHERE token_hash = %s", (token_hash,))

    def remove_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str, *, tx: Executor | None = None
    ) -> None:
        (tx or self._db).execute(
            "DELETE FROM api_tokens WHERE principal_type = %s AND principal_id = %s",
            (principal_type.value, principal_id),
        )

    def remove_channel_bindings_for_principal(
        self,
        channel: Channel,
        principal_type: PrincipalType,
        principal_id: str,
        *,
        tx: Executor | None = None,
    ) -> None:
        (tx or self._db).execute(
            "DELETE FROM channel_bindings "
            "WHERE channel = %s AND principal_type = %s AND principal_id = %s",
            (channel.value, principal_type.value, principal_id),
        )


class FakeAccountStore:
    """AccountStore 的記憶體替身（測試用，不碰 DB）。

    `transaction()` 與 Pg 對齊回滾語意（✅ 庚-18）：交易內任何例外 → 還原全部
    狀態後重拋。`tx` 參數在本替身仍被忽略（寫入直接進 dict），原子性由快照達成。
    """

    _STATE_DICTS = (
        "elders",
        "guardians",
        "elder_guardians",
        "consents",
        "invites",
        "channel_bindings",
        "guardian_accounts",
        "elder_accounts",
        "api_tokens",
    )

    def __init__(self) -> None:
        self.elders: dict[str, Elder] = {}
        self.guardians: dict[str, Guardian] = {}
        self.elder_guardians: dict[tuple[str, str], ElderGuardian] = {}
        self.consents: dict[str, Consent] = {}
        self.invites: dict[str, Invite] = {}
        self.channel_bindings: dict[tuple[Channel, str], ChannelBinding] = {}
        self.guardian_accounts: dict[str, GuardianAccount] = {}
        self.elder_accounts: dict[str, ElderAccount] = {}
        self.api_tokens: dict[str, ApiToken] = {}

    @contextmanager
    def transaction(self) -> Iterator[None]:
        # 淺複製快照即可：值皆為 frozen dataclass，不會就地變異。
        snapshot = {name: dict(getattr(self, name)) for name in self._STATE_DICTS}
        try:
            yield None
        except Exception:
            for name, value in snapshot.items():
                setattr(self, name, value)
            raise

    def save_elder(self, elder: Elder, *, tx: Executor | None = None) -> None:
        self.elders[elder.elder_id] = elder

    def get_elder(self, elder_id: str) -> Elder | None:
        return self.elders.get(elder_id)

    def save_guardian(self, guardian: Guardian, *, tx: Executor | None = None) -> None:
        self.guardians[guardian.guardian_id] = guardian

    def get_guardian_by_line(self, line_user_id: str) -> Guardian | None:
        # 讀取端已切經 channel_bindings（1C），與 Pg 同形。
        binding = self.get_channel_binding(Channel.LINE, line_user_id)
        if binding is None or binding.principal_type is not PrincipalType.GUARDIAN:
            return None
        return self.get_guardian(binding.principal_id)

    def get_elder_by_line(self, line_user_id: str) -> Elder | None:
        binding = self.get_channel_binding(Channel.LINE, line_user_id)
        if binding is None or binding.principal_type is not PrincipalType.ELDER:
            return None
        return self.get_elder(binding.principal_id)

    def get_guardian(self, guardian_id: str) -> Guardian | None:
        return self.guardians.get(guardian_id)

    def save_elder_guardian(self, eg: ElderGuardian, *, tx: Executor | None = None) -> None:
        self.elder_guardians[(eg.elder_id, eg.guardian_id)] = eg

    def list_elder_guardians(self, elder_id: str) -> list[ElderGuardian]:
        rows = [v for (e, _), v in self.elder_guardians.items() if e == elder_id]
        return sorted(rows, key=lambda x: x.escalation_order)

    def elder_ids_of_guardian(self, guardian_id: str) -> list[str]:
        return sorted(e for (e, g) in self.elder_guardians if g == guardian_id)

    def save_consent(self, consent: Consent, *, tx: Executor | None = None) -> None:
        self.consents[consent.elder_id] = consent

    def get_consent(self, elder_id: str) -> Consent | None:
        return self.consents.get(elder_id)

    def save_invite(self, invite: Invite, *, tx: Executor | None = None) -> None:
        self.invites[invite.code] = invite

    def get_invite(
        self, code: str, *, tx: Executor | None = None, for_update: bool = False
    ) -> Invite | None:
        return self.invites.get(code)

    def list_invites_for_elder(self, elder_id: str) -> list[Invite]:
        rows = [i for i in self.invites.values() if i.elder_id == elder_id]
        return sorted(rows, key=lambda i: i.expires_at, reverse=True)

    def save_channel_binding(self, binding: ChannelBinding, *, tx: Executor | None = None) -> None:
        key = (binding.channel, binding.external_id)
        existing = self.channel_bindings.get(key)
        if existing is not None:
            # 與 Pg 一致：upsert 不覆寫 created_at（保留首次綁定時間）。
            binding = ChannelBinding(
                binding.channel,
                binding.external_id,
                binding.principal_type,
                binding.principal_id,
                existing.created_at,
            )
        self.channel_bindings[key] = binding

    def get_channel_binding(self, channel: Channel, external_id: str) -> ChannelBinding | None:
        return self.channel_bindings.get((channel, external_id))

    def list_channel_bindings_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ChannelBinding]:
        rows = [
            b
            for b in self.channel_bindings.values()
            if b.principal_type == principal_type and b.principal_id == principal_id
        ]
        return sorted(rows, key=lambda b: (b.channel.value, b.external_id))

    def save_guardian_account(
        self, account: GuardianAccount, *, tx: Executor | None = None
    ) -> None:
        self.guardian_accounts[account.guardian_id] = account

    def get_guardian_account_by_email(self, email: str) -> GuardianAccount | None:
        return next((a for a in self.guardian_accounts.values() if a.email == email), None)

    def save_elder_account(self, account: ElderAccount, *, tx: Executor | None = None) -> None:
        self.elder_accounts[account.elder_id] = account

    def get_elder_account_by_phone(self, phone: str) -> ElderAccount | None:
        return next((a for a in self.elder_accounts.values() if a.phone == phone), None)

    def get_elder_account(self, elder_id: str) -> ElderAccount | None:
        return self.elder_accounts.get(elder_id)

    def save_api_token(self, token: ApiToken, *, tx: Executor | None = None) -> None:
        # 與 Pg 一致：ON CONFLICT DO NOTHING（token_hash 不覆寫）。
        self.api_tokens.setdefault(token.token_hash, token)

    def get_api_token(self, token_hash: str) -> ApiToken | None:
        return self.api_tokens.get(token_hash)

    def list_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ApiToken]:
        rows = [
            t
            for t in self.api_tokens.values()
            if t.principal_type is principal_type and t.principal_id == principal_id
        ]
        return sorted(rows, key=lambda t: t.created_at, reverse=True)

    def remove_api_token(self, token_hash: str) -> None:
        self.api_tokens.pop(token_hash, None)

    def remove_api_tokens_for_principal(
        self, principal_type: PrincipalType, principal_id: str, *, tx: Executor | None = None
    ) -> None:
        self.api_tokens = {
            h: t
            for h, t in self.api_tokens.items()
            if not (t.principal_type is principal_type and t.principal_id == principal_id)
        }

    def remove_channel_bindings_for_principal(
        self,
        channel: Channel,
        principal_type: PrincipalType,
        principal_id: str,
        *,
        tx: Executor | None = None,
    ) -> None:
        self.channel_bindings = {
            key: b
            for key, b in self.channel_bindings.items()
            if not (
                b.channel is channel
                and b.principal_type is principal_type
                and b.principal_id == principal_id
            )
        }
