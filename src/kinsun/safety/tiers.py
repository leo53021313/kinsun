"""危急分級的資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskTier(IntEnum):
    L0 = 0  # 一般
    L1 = 1  # 關注
    L2 = 2  # 警示
    L3 = 3  # 緊急


# 分級器故障時保守留痕事件的固定理由（✅ D-31，甲-5）。
# events 的 fail-safe 計數與 admin 告警都以此字串辨識，勿隨意改字。
FAILSAFE_EVENT_REASON = "分級器故障，保守留痕"


@dataclass(frozen=True)
class RiskAssessment:
    tier: RiskTier
    confidence: float
    reason: str
    signals: list[str] = field(default_factory=list)
