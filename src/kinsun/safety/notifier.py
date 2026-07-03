"""危急通知。`LogNotifier` 為 placeholder；`LineGuardianNotifier` 推播給已綁定家屬。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.safety.tiers import RiskAssessment, RiskTier

logger = logging.getLogger("kinsun.safety")


class Notifier(Protocol):
    def notify(self, line_user_id: str, assessment: RiskAssessment) -> None: ...


class LogNotifier:
    def notify(self, line_user_id: str, assessment: RiskAssessment) -> None:
        logger.warning(
            "危急通知 session=%s tier=%s confidence=%.2f reason=%s signals=%s",
            line_user_id,
            assessment.tier.name,
            assessment.confidence,
            assessment.reason,
            assessment.signals,
        )


class GuardianDirectory(Protocol):
    def guardian_line_ids(self, line_user_id: str) -> list[str]: ...


class Pusher(Protocol):
    def push_text(self, line_user_id: str, text: str) -> None: ...


_ALERT_PREFIX = "⚠️【金孫關懷提醒】"


def _format_alert(assessment: RiskAssessment) -> str:
    text = (
        f"{_ALERT_PREFIX}您關心的長輩可能需要您的注意："
        f"{assessment.reason}（風險等級 {assessment.tier.name}）。請盡快主動關心一下。"
    )
    if assessment.tier == RiskTier.L3:
        text += "（如情況緊急，請自行評估是否撥打 119。金孫不提供醫療診斷。）"
    return text


class LineGuardianNotifier:
    """危急時依升級順序推播給所有家屬。任何失敗只記錄、不中斷對話。"""

    def __init__(self, directory: GuardianDirectory, pusher: Pusher) -> None:
        self._directory = directory
        self._pusher = pusher

    def notify(self, line_user_id: str, assessment: RiskAssessment) -> None:
        try:
            targets = self._directory.guardian_line_ids(line_user_id)
            if not targets:
                logger.warning(
                    "危急但查無可通知家屬 session=%s tier=%s reason=%s",
                    line_user_id,
                    assessment.tier.name,
                    assessment.reason,
                )
                return
            text = _format_alert(assessment)
            sent = 0
            # 迴圈變數帶 guardian_ 限定詞，避免與外層 line_user_id（長輩本人）同名遮蔽。
            for guardian_line_user_id in targets:
                try:
                    self._pusher.push_text(guardian_line_user_id, text)
                    sent += 1
                except Exception:  # noqa: BLE001
                    logger.exception("推播家屬失敗 guardian_line_user_id=%s", guardian_line_user_id)
            logger.warning(
                "已通知家屬 session=%s tier=%s 成功=%d/%d",
                line_user_id,
                assessment.tier.name,
                sent,
                len(targets),
            )
        except Exception:  # noqa: BLE001
            logger.exception("家屬通知流程異常 session=%s", line_user_id)
