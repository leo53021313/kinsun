"""通道中立的入站訊息與分派（不依賴任何特定通道 SDK）。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from kinsun.llm import LLMError
from kinsun.memory.store import MemoryError
from kinsun.speech.asr import ASRError

logger = logging.getLogger("kinsun.inbound")

NON_AUDIO_PROMPT = "金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
FALLBACK_PROMPT = "金孫剛剛沒聽清楚，您可以再說一次嗎？"
BIND_FIRST_PROMPT = (
    "金孫需要先完成綁定才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


@dataclass(frozen=True)
class InboundMessage:
    """通道中立的入站訊息。kind ∈ text/audio/other；reply 為綁定好的回覆 handle，
    reply_voice 為語音回覆 handle（url、duration_ms、text）。"""

    session_id: str
    kind: str
    text: str
    audio: bytes
    reply: Callable[[str], None]
    reply_voice: Callable[[str, int, str | None], None] | None = None


def dispatch(msg: InboundMessage, *, pipeline, binding, gate) -> None:
    if msg.kind == "text":
        reply = binding.handle(msg.session_id, msg.text)
        msg.reply(reply if reply is not None else NON_AUDIO_PROMPT)
        return
    if msg.kind != "audio":
        msg.reply(NON_AUDIO_PROMPT)
        return
    if not gate.allows(msg.session_id):
        msg.reply(BIND_FIRST_PROMPT)
        return
    try:
        result = pipeline.process(msg.audio, session_id=msg.session_id)
        msg.reply(result.text)
    except (ASRError, LLMError, MemoryError):
        msg.reply(FALLBACK_PROMPT)
