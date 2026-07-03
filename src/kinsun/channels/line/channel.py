"""LINE 通道轉接器：把 LINE webhook 事件正規化成 InboundMessage，並記錄觀測事件。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from kinsun.channels.inbound import InboundMessage
from kinsun.channels.line.messenger import LineMessenger
from kinsun.observability.store import TraceStore, safe_record

logger = logging.getLogger("kinsun.channels.line")


def _event_payload(event) -> dict:
    """把 LINE SDK 事件轉成可 JSON 序列化的 dict；失敗退回 repr。"""
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:  # noqa: BLE001 - 序列化失敗不可中斷
            pass
    return {"repr": repr(event)}


class LineChannel:
    def __init__(
        self,
        messenger: LineMessenger,
        *,
        traces: TraceStore | None = None,
        inbound_audio=None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._messenger = messenger
        self._traces = traces
        self._inbound_audio = inbound_audio
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    def inbound(self, event) -> InboundMessage | None:
        message = getattr(event, "message", None)
        reply_token = getattr(event, "reply_token", None)
        if message is None or reply_token is None:
            return None
        source = getattr(event, "source", None)
        line_user_id = getattr(source, "user_id", None) or "unknown"
        mtype = getattr(message, "type", None)
        trace_id = self._new_id()
        self._record_event(event, trace_id, line_user_id, mtype)

        def reply(text: str) -> None:
            self._messenger.reply_text(reply_token, text)

        def reply_voice(audio_url: str, duration_ms: int, text: str | None) -> None:
            self._messenger.reply_voice(reply_token, audio_url, duration_ms, text)

        if mtype == "text":
            return InboundMessage(
                line_user_id,
                "text",
                getattr(message, "text", "") or "",
                b"",
                reply,
                reply_voice,
                trace_id=trace_id,
            )
        if mtype == "audio":
            audio = self._messenger.get_audio(message.id)
            return InboundMessage(
                line_user_id,
                "audio",
                "",
                audio,
                reply,
                reply_voice,
                trace_id=trace_id,
                audio_url=self._publish_inbound(audio),
            )
        return InboundMessage(line_user_id, "other", "", b"", reply, reply_voice, trace_id=trace_id)

    def _record_event(self, event, trace_id: str, line_user_id: str, mtype) -> None:
        if self._traces is None:
            return
        traces = self._traces
        safe_record(
            lambda: traces.record_webhook_event(
                trace_id=trace_id,
                line_user_id=line_user_id,
                event_type=str(getattr(event, "type", "") or "unknown"),
                message_type=str(mtype or ""),
                payload=_event_payload(event),
            )
        )

    def _publish_inbound(self, audio: bytes) -> str:
        if self._inbound_audio is None:
            return ""
        try:
            return self._inbound_audio.publish(audio, content_type="audio/m4a")
        except Exception:  # noqa: BLE001 - 上傳失敗不可中斷對話
            logger.warning("進站音檔上傳失敗")
            return ""
