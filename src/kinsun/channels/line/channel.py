"""LINE 通道轉接器：把 LINE webhook 事件正規化成 InboundMessage。"""

from __future__ import annotations

from kinsun.channels.inbound import InboundMessage
from kinsun.channels.line.messenger import LineMessenger


class LineChannel:
    def __init__(self, messenger: LineMessenger) -> None:
        self._messenger = messenger

    def inbound(self, event) -> InboundMessage | None:
        message = getattr(event, "message", None)
        reply_token = getattr(event, "reply_token", None)
        if message is None or reply_token is None:
            return None
        source = getattr(event, "source", None)
        session_id = getattr(source, "user_id", None) or "unknown"
        mtype = getattr(message, "type", None)

        def reply(text: str) -> None:
            self._messenger.reply_text(reply_token, text)

        if mtype == "text":
            return InboundMessage(
                session_id, "text", getattr(message, "text", "") or "", b"", reply
            )
        if mtype == "audio":
            return InboundMessage(
                session_id, "audio", "", self._messenger.get_audio(message.id), reply
            )
        return InboundMessage(session_id, "other", "", b"", reply)
