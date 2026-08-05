"""帳號綁定的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kinsun.personas import DEFAULT_PERSONA_ID


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
    # 稱謂（如「秀英阿嬤」）：金孫對長輩的稱呼，由家屬設定。空字串＝未設定，
    # 情境注入退回「用名字＋不猜性別」（2026-07-17：模型會亂猜阿公／阿嬤）。
    nickname: str = ""
    # 人設（2026-08-05）：金孫對這位長輩用哪一種語氣，由家屬設定。值域見
    # `personas.py`；不認得的值由 `personas.get_persona` 退回預設，不會壞。
    persona: str = DEFAULT_PERSONA_ID


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
class ElderAccount:
    """長輩的 App 登入帳號（✅ D-71 己-6）：手機號碼＋密碼雜湊，由家屬代辦。"""

    elder_id: str
    phone: str
    password_hash: str
    created_at: float


@dataclass(frozen=True)
class ApiToken:
    """API token 發放紀錄：DB 只存 SHA-256 雜湊，明文只在發放當下回傳一次。"""

    token_hash: str
    principal_type: PrincipalType
    principal_id: str
    created_at: float
