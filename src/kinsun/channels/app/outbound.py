"""App 通道出站 adapter（✅ D-12，甲-6）：訊息持久化為 App 內通知。

與 LINE 的 LineOutboundChannel 對稱地掛在 ChannelRouter 上。落一筆
`app_notifications` 是**保證留存**的路徑：家屬走 `GET /notifications`、
長輩走 `GET /elder-notifications`（X-01，2026-07-29）拉取。

真推播（D-08 階段 5，2026-07-29）：落庫之後**再**推一則到使用者的裝置。
順序不可顛倒，例外也不可外洩——推播是加分項（App 沒開、token 失效、換手機時
必然推不到），但落庫失敗訊息就真的消失了。
"""

from __future__ import annotations

import logging

from kinsun.notifications.models import NotificationSeverity
from kinsun.notifications.push_delivery import PushDelivery
from kinsun.notifications.store import AppNotificationStore

logger = logging.getLogger("kinsun.outbound")


class AppOutboundChannel:
    def __init__(
        self, notifications: AppNotificationStore, *, push: PushDelivery | None = None
    ) -> None:
        self._notifications = notifications
        self._push = push

    def send_text(
        self,
        external_id: str,
        text: str,
        *,
        severity: NotificationSeverity = NotificationSeverity.NOTICE,
    ) -> None:
        """落庫（帶呈現分級）→ 再推播。

        ⚠️ `severity` **只落庫、不影響推播**（2026-08-01 的刻意範圍限制）：Expo
        推播另有自己的 priority／channelId 概念，要接是另一包工作（含 Android
        通知頻道註冊），且推播本身是加分項。這一輪要修的是「畫面上分不出來」，
        落庫這一段就足夠——`GET /notifications` 與 `/elder-notifications` 是
        保證留存的那條路徑，前端橫幅讀的正是它。
        """
        self._notifications.record(external_id, text, severity=severity)
        if self._push is None:
            return
        try:
            self._push.push(external_id, text)
        except Exception:  # noqa: BLE001 - 推播失敗不可讓已落庫的通知看起來像沒送出
            logger.warning("裝置推播失敗（訊息已落庫，App 開啟時仍看得到）")
