"""App 通道出站 adapter（✅ D-12，甲-6）：訊息持久化為 App 內通知。

與 LINE 的 LineOutboundChannel 對稱地掛在 ChannelRouter 上；真推播（D-08
階段 5）到位前，「送出」＝落一筆 app_notifications，App 端登入後拉取顯示。
"""

from __future__ import annotations

from kinsun.notifications.store import AppNotificationStore


class AppOutboundChannel:
    def __init__(self, notifications: AppNotificationStore) -> None:
        self._notifications = notifications

    def send_text(self, external_id: str, text: str) -> None:
        self._notifications.record(external_id, text)
