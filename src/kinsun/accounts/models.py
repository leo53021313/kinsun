"""帳號綁定的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    PRIMARY = "primary"
    GUARDIAN = "guardian"


class InviteRole(StrEnum):
    ELDER = "elder"
    GUARDIAN = "guardian"


class ConsentBy(StrEnum):
    SELF = "self"
    PROXY = "proxy"


@dataclass(frozen=True)
class Elder:
    elder_id: str
    name: str


@dataclass(frozen=True)
class Guardian:
    guardian_id: str
    name: str


@dataclass(frozen=True)
class ElderGuardian:
    elder_id: str
    guardian_id: str
    role: Role
    # escalation_order 保留（✅ 己-8 決議）：升級鏈不做（D-10），但家屬通知與清單順序仍靠它。
    escalation_order: int


@dataclass(frozen=True)
class Consent:
    elder_id: str
    consent_by: ConsentBy
    version: str
    granted_at: float
    revoked_at: float | None = None


@dataclass(frozen=True)
class Invite:
    code: str
    elder_id: str
    role: InviteRole
    expires_at: float
    max_attempts: int
    attempts: int = 0
    used_at: float | None = None


class Channel(StrEnum):
    LINE = "line"
    APP = "app"


class PrincipalType(StrEnum):
    ELDER = "elder"
    GUARDIAN = "guardian"


@dataclass(frozen=True)
class ChannelBinding:
    """通道帳號 → 本人（長輩／家屬）的對應：一人可同時有多通道綁定。"""

    channel: Channel
    external_id: str
    principal_type: PrincipalType
    principal_id: str
    created_at: float


@dataclass(frozen=True)
class GuardianAccount:
    """家屬的 App 登入帳號：email＋密碼雜湊（scrypt，見 accounts/passwords.py）。"""

    guardian_id: str
    email: str
    password_hash: str
    created_at: float


@dataclass(frozen=True)
class ApiToken:
    """API token 發放紀錄：DB 只存 SHA-256 雜湊，明文只在發放當下回傳一次。"""

    token_hash: str
    principal_type: PrincipalType
    principal_id: str
    created_at: float
