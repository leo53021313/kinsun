"""知識圖譜的資料結構。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Provenance(StrEnum):
    SELF_CLAIMED = "self_claimed"  # 本人自述
    INFERRED = "inferred"  # 推測
    FAMILY_CONFIRMED = "family_confirmed"  # 家屬確認（綁定後才會用）


class FactCategory(StrEnum):
    PROFILE = "profile"
    FAMILY = "family"
    MEDICATION = "medication"
    CONDITION = "condition"
    EVENT = "event"
    OTHER = "other"


@dataclass(frozen=True)
class Fact:
    session_id: str
    category: FactCategory
    content: str
    provenance: Provenance
    confidence: float
