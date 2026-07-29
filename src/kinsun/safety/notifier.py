"""危急通知。`LogNotifier` 為 placeholder；`GuardianNotifier` 依綁定通道推播給所有家屬。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun import tracing
from kinsun.accounts.models import ElderGuardian, PrincipalType
from kinsun.safety.tiers import RiskAssessment, RiskTier

logger = logging.getLogger("kinsun.safety")


class Notifier(Protocol):
    def notify(self, elder_id: str, assessment: RiskAssessment, user_text: str) -> None: ...


class TextSender(Protocol):
    """「可送文字」插座（✅ D-18）：safety 核心只依賴此抽象，
    不 import 邊緣層的 channels.router——組裝處把 ChannelRouter 插進來。
    回傳實際成功的通道名（✅ 庚-16），供送達留痕標註語意。

    `has_route` 供「還沒綁通道」與「送出失敗」分流（2026-07-27）：兩者的
    `send_text_channels` 回傳都是空清單，光看結果分不出來。"""

    def has_route(self, principal_type: PrincipalType, principal_id: str) -> bool: ...
    def send_text_channels(
        self, principal_type: PrincipalType, principal_id: str, text: str
    ) -> list[str]: ...


class LogNotifier:
    def notify(self, elder_id: str, assessment: RiskAssessment, user_text: str) -> None:
        # reason（分級器對長輩健康狀態的描述）與 user_text（長輩原話）都是對話內容，
        # 不進 log（2026-07-27 政策）。
        logger.warning(
            "危急通知 elder=%s tier=%s confidence=%.2f signals=%s",
            elder_id,
            assessment.tier.name,
            assessment.confidence,
            assessment.signals,
        )


class GuardianDirectory(Protocol):
    def guardians_of(self, elder_id: str) -> list[ElderGuardian]: ...


_ALERT_PREFIX = "⚠️【金孫關懷提醒】"


def _format_alert(assessment: RiskAssessment, user_text: str) -> str:
    # 文案只引長輩原話（2026-07-29 Leo 定案）：緊不緊急由家屬自行判斷，不轉述
    # 分級器的 reason，也不放家屬看不懂的「風險等級」字樣。語音輪次的原話是
    # ASR 轉出的文字（可能有錯字），Leo 同日核定不加辨識註記、直接呈現。
    text = f"{_ALERT_PREFIX}\n您關心的長輩剛剛說：\n「{user_text}」\n請盡快主動關心一下。"
    # L3 刪除後（✅ D-72），119 提示改掛「絕對危急詞命中」訊號——tier 已無法區分。
    if "keyword:absolute" in assessment.signals:
        text += "\n（如情況緊急，請自行評估是否撥打 119。金孫不提供醫療診斷。）"
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
        outcome: str = "",
    ) -> None: ...


# 送達結果分類（寫進 risk_notification_logs.outcome）。`no_route` 是常態不是故障，
# admin 的投遞失敗告警只算 `failed`——見 deliveries.count_failed_since。
_OUTCOME_SENT = "sent"
_OUTCOME_NO_ROUTE = "no_route"
_OUTCOME_FAILED = "failed"


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
        self, elder_id: str, guardian_id: str, tier, *, delivered: bool, channels: str, outcome: str
    ) -> None:
        if self._deliveries is None:
            return
        try:
            self._deliveries.record(
                elder_id,
                guardian_id,
                tier,
                delivered=delivered,
                channels=channels,
                outcome=outcome,
            )
        except Exception:  # noqa: BLE001 - 留痕失敗不可反噬通知
            logger.warning("送達紀錄寫入失敗 elder=%s guardian=%s", elder_id, guardian_id)

    @tracing.track(name="guardian_notify", type="general", capture_input=True, capture_output=True)
    def notify(self, elder_id: str, assessment: RiskAssessment, user_text: str) -> None:
        try:
            targets = [eg.guardian_id for eg in self._directory.guardians_of(elder_id)]
            if not targets:
                # ⚠️ 刻意不印 assessment.reason（2026-07-27 政策，Leo 定案）：那是分級器
                # 對長輩健康狀態的描述，屬對話內容，只進 Opik（`risk_assess` span 的輸出）
                # 與 risk_events 表。這裡印訊號名——那是系統事實（哪條規則命中）。
                logger.warning(
                    "危急但查無可通知家屬 elder=%s tier=%s 訊號=%s",
                    elder_id,
                    assessment.tier.name,
                    ",".join(assessment.signals),
                )
                return
            text = _format_alert(assessment, user_text)
            sent = 0
            unbound = 0
            for guardian_id in targets:
                # 先問有沒有可達通道（2026-07-27）：沒綁通道與送出失敗的
                # `send_text_channels` 回傳都是空清單，事後分不出來，只能事前問。
                # 沒有通道就不必白呼叫一次出站，但仍要留痕——稽核問的是「家屬當時
                # 有沒有收到」，沒收到就是沒收到，理由記在 outcome。
                if not self._router.has_route(PrincipalType.GUARDIAN, guardian_id):
                    unbound += 1
                    self._record_delivery(
                        elder_id,
                        guardian_id,
                        assessment.tier,
                        delivered=False,
                        channels="",
                        outcome=_OUTCOME_NO_ROUTE,
                    )
                    continue
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
                    outcome=_OUTCOME_SENT if delivered else _OUTCOME_FAILED,
                )
            logger.warning(
                "已通知家屬 elder=%s tier=%s 成功=%d/%d（其中 %d 位尚未綁定通道）",
                elder_id,
                assessment.tier.name,
                sent,
                len(targets),
                unbound,
            )
        except Exception:  # noqa: BLE001
            logger.exception("家屬通知流程異常 elder=%s", elder_id)
