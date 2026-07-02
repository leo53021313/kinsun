"""危急分級的資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskTier(IntEnum):
    L0 = 0  # 一般
    L1 = 1  # 關注
    L2 = 2  # 警示
    L3 = 3  # 緊急


@dataclass(frozen=True)
class RiskAssessment:
    tier: RiskTier
    confidence: float
    reason: str
    signals: list[str] = field(default_factory=list)
