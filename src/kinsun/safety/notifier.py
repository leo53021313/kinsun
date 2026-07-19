"""危急通知。`LogNotifier` 為 placeholder；`GuardianNotifier` 依綁定通道推播給所有家屬。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun import tracing
from kinsun.accounts.models import ElderGuardian, PrincipalType
from kinsun.safety.tiers import RiskAssessment, RiskTier

logger = logging.getLogger("kinsun.safety")


class Notifier(Protocol):
    def notify(self, elder_id: str, assessment: RiskAssessment) -> None: ...


class TextSender(Protocol):
    """「可送文字」插座（✅ D-18）：safety 核心只依賴此抽象，
    不 import 邊緣層的 channels.router——組裝處把 ChannelRouter 插進來。
    回傳實際成功的通道名（✅ 庚-16），供送達留痕標註語意。"""

    def send_text_channels(
        self, principal_type: PrincipalType, principal_id: str, text: str
    ) -> list[str]: ...


class LogNotifier:
    def notify(self, elder_id: str, assessment: RiskAssessment) -> None:
        logger.warning(
            "危急通知 elder=%s tier=%s confidence=%.2f reason=%s signals=%s",
            elder_id,
            assessment.tier.name,
            assessment.confidence,
            assessment.reason,
            assessment.signals,
        )


class GuardianDirectory(Protocol):
    def guardians_of(self, elder_id: str) -> list[ElderGuardian]: ...


_ALERT_PREFIX = "⚠️【金孫關懷提醒】"


def _format_alert(assessment: RiskAssessment) -> str:
    text = (
        f"{_ALERT_PREFIX}您關心的長輩可能需要您的注意："
        f"{assessment.reason}（風險等級 {assessment.tier.name}）。請盡快主動關心一下。"
    )
    # L3 刪除後（✅ D-72），119 提示改掛「絕對危急詞命中」訊號——tier 已無法區分。
    if "keyword:absolute" in assessment.signals:
        text += "（如情況緊急，請自行評估是否撥打 119。金孫不提供醫療診斷。）"
    return text


class DeliveryLog(Protocol):
    """送達留痕插座（✅ D-36）：每位家屬成功／失敗各記一筆；
    channels 記實際走的通道（✅ 庚-16，逗號串接），App＝落庫待拉取而非真送達。"""

    def record(
        self,
        elder_id: str,
        guardian_id: str,
        tier: RiskTier,
        *,
        delivered: bool,
        channels: str = "",
    ) -> None: ...


class GuardianNotifier:
    """危急時依升級順序、經綁定通道推播給所有家屬。任何失敗只記錄、不中斷對話。"""

    def __init__(
        self,
        directory: GuardianDirectory,
        router: TextSender,
        *,
        deliveries: DeliveryLog | None = None,
    ) -> None:
        self._directory = directory
        self._router = router
        self._deliveries = deliveries

    def _record_delivery(
        self, elder_id: str, guardian_id: str, tier, *, delivered: bool, channels: str
    ) -> None:
        if self._deliveries is None:
            return
        try:
            self._deliveries.record(
                elder_id, guardian_id, tier, delivered=delivered, channels=channels
            )
        except Exception:  # noqa: BLE001 - 留痕失敗不可反噬通知
            logger.warning("送達紀錄寫入失敗 elder=%s guardian=%s", elder_id, guardian_id)

    @tracing.track(
        name="guardian_notify", type="general", capture_input=False, capture_output=False
    )
    def notify(self, elder_id: str, assessment: RiskAssessment) -> None:
        try:
            targets = [eg.guardian_id for eg in self._directory.guardians_of(elder_id)]
            if not targets:
                logger.warning(
                    "危急但查無可通知家屬 elder=%s tier=%s reason=%s",
                    elder_id,
                    assessment.tier.name,
                    assessment.reason,
                )
                return
            text = _format_alert(assessment)
            sent = 0
            for guardian_id in targets:
                channels = self._router.send_text_channels(
                    PrincipalType.GUARDIAN, guardian_id, text
                )
                delivered = bool(channels)
                if delivered:
                    sent += 1
                # 送達與否獨立留痕（✅ D-36）：「家屬當時有沒有收到」查得到；
                # 通道一併記下（✅ 庚-16）——App 僅為落庫待拉取，語意由通道還原。
                self._record_delivery(
                    elder_id,
                    guardian_id,
                    assessment.tier,
                    delivered=delivered,
                    channels=",".join(channels),
                )
            logger.warning(
                "已通知家屬 elder=%s tier=%s 成功=%d/%d",
                elder_id,
                assessment.tier.name,
                sent,
                len(targets),
            )
        except Exception:  # noqa: BLE001
            logger.exception("家屬通知流程異常 elder=%s", elder_id)
