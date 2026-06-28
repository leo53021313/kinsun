"""危急通知（placeholder）。家屬綁定未建前，僅結構化記錄，不真的通知家屬。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.safety.tiers import RiskAssessment

logger = logging.getLogger("kinsun.safety")


class Notifier(Protocol):
    def notify(self, session_id: str, assessment: RiskAssessment) -> None: ...


class LogNotifier:
    def notify(self, session_id: str, assessment: RiskAssessment) -> None:
        logger.warning(
            "危急通知 session=%s tier=%s confidence=%.2f reason=%s signals=%s",
            session_id,
            assessment.tier.name,
            assessment.confidence,
            assessment.reason,
            assessment.signals,
        )
