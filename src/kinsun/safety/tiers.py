"""危急分級的資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskTier(IntEnum):
    """三級制（✅ D-72，己-4）：L2 為頂級、達 L2 即通知家屬；L1 進每日摘要不即時通知。"""

    L0 = 0  # 一般
    L1 = 1  # 小訊號
    L2 = 2  # 明確警訊


def tier_from_db(value: int) -> RiskTier:
    """讀 DB 的 tier 欄：四級制時代的舊資料（3）夾回 L2，不炸也不流失。"""
    return RiskTier(min(int(value), RiskTier.L2))


# 分級器故障時保守留痕事件的固定理由（✅ D-31，甲-5）。
# events 的 fail-safe 計數與 admin 告警都以此字串辨識，勿隨意改字。
FAILSAFE_EVENT_REASON = "分級器故障，保守留痕"


@dataclass(frozen=True)
class RiskAssessment:
    tier: RiskTier
    confidence: float
    reason: str
    signals: list[str] = field(default_factory=list)
