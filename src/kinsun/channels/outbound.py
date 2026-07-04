"""通道中立的出站門面：主動送訊息給長輩／家屬（不依賴任何特定通道 SDK）。

與入站的 InboundMessage 對稱。主動關懷、提醒 jobs、危急通知皆依賴此門面；
LINE 版 LineOutboundChannel 為 adapter（見 channels/line/messenger.py）。
未來若要主動語音，於此 Protocol 再加 send_voice。
"""

from __future__ import annotations

from typing import Protocol


class OutboundChannel(Protocol):
    def send_text(self, line_user_id: str, text: str) -> None: ...


class FakeOutboundChannel:
    """OutboundChannel 的測試替身：記錄每次送出的 (line_user_id, text)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_text(self, line_user_id: str, text: str) -> None:
        self.sent.append((line_user_id, text))
