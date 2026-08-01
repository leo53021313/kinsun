"""通道中立的出站門面：對單一通道帳號送訊息（不依賴任何特定通道 SDK）。

與入站的 InboundMessage 對稱。external_id 為該通道的帳號識別（LINE userId／
App 裝置帳號）；「本人 → 通道」的選路由 channels/router.py 的 ChannelRouter 負責，
主動關懷、提醒 jobs、危急通知皆依賴 router，不直接呼叫本門面。
LINE 版 LineOutboundChannel 為 adapter（見 channels/line/messenger.py）。
未來若要主動語音，於此 Protocol 再加 send_voice。
"""

from __future__ import annotations

from typing import Protocol

from kinsun.notifications.models import NotificationSeverity


class OutboundChannel(Protocol):
    """⚠️ `severity` 是**給得起的通道就用，給不起的就忽略**（2026-08-01）。

    它描述的是「收到的人畫面上該不該被打斷」，只有 App 通道落得了地
    （`app_notifications.severity`）；LINE 的純文字訊息沒有樣式概念，
    `LineOutboundChannel` 明文忽略它。預設 `NOTICE`——既有呼叫端不必全部改，
    且「沒特別說就是一般通知」是唯一安全的預設：預設 ALERT 會讓每一則用藥
    提醒都變成紅色警報。
    """

    def send_text(
        self,
        external_id: str,
        text: str,
        *,
        severity: NotificationSeverity = NotificationSeverity.NOTICE,
    ) -> None: ...


class FakeOutboundChannel:
    """OutboundChannel 的測試替身：記錄每次送出的 (external_id, text)。

    ⚠️ `sent` 刻意維持二元組不動（既有測試多處對它做等值斷言）；severity 另記
    在 `sent_severities` 供需要的測試查——把它塞進 `sent` 會讓每一支既有斷言
    都得改，而那些斷言與 severity 無關。
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.sent_severities: list[NotificationSeverity] = []

    def send_text(
        self,
        external_id: str,
        text: str,
        *,
        severity: NotificationSeverity = NotificationSeverity.NOTICE,
    ) -> None:
        self.sent.append((external_id, text))
        self.sent_severities.append(severity)
