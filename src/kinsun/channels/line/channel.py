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
        line_user_id = getattr(source, "user_id", None) or "unknown"
        mtype = getattr(message, "type", None)

        def reply(text: str) -> None:
            self._messenger.reply_text(reply_token, text)

        def reply_voice(audio_url: str, duration_ms: int, text: str | None) -> None:
            self._messenger.reply_voice(reply_token, audio_url, duration_ms, text)

        if mtype == "text":
            return InboundMessage(
                line_user_id, "text", getattr(message, "text", "") or "", b"", reply, reply_voice
            )
        if mtype == "audio":
            return InboundMessage(
                line_user_id,
                "audio",
                "",
                self._messenger.get_audio(message.id),
                reply,
                reply_voice,
            )
        return InboundMessage(line_user_id, "other", "", b"", reply, reply_voice)
