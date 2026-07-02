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
    line_user_id: str | None = None


@dataclass(frozen=True)
class Guardian:
    guardian_id: str
    line_user_id: str
    name: str


@dataclass(frozen=True)
class ElderGuardian:
    elder_id: str
    guardian_id: str
    role: Role
    escalation_order: int
    can_view_transcript: bool


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
