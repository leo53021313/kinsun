"""通道中立的入站訊息與分派（不依賴任何特定通道 SDK）。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from kinsun.llm import LLMError
from kinsun.memory.shortterm import MemoryError
from kinsun.observability.store import TraceStore, safe_record
from kinsun.speech.asr import ASRError
from kinsun.speech.tts import TtsResult

logger = logging.getLogger("kinsun.inbound")

NON_AUDIO_PROMPT = "金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
FALLBACK_PROMPT = "金孫剛剛沒聽清楚，您可以再說一次嗎？"
BIND_FIRST_PROMPT = (
    "金孫需要先完成綁定才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


@dataclass(frozen=True)
class InboundMessage:
    """通道中立的入站訊息。kind ∈ text/audio/other；reply 為綁定好的回覆 handle，
    reply_voice 為語音回覆 handle（url、duration_ms、text）。
    trace_id／audio_url 供觀測鏈路與音檔回放（無觀測時為空字串）。"""

    line_user_id: str
    kind: str
    text: str
    audio: bytes
    reply: Callable[[str], None]
    reply_voice: Callable[[str, int, str | None], None] | None = None
    trace_id: str = ""
    audio_url: str = ""


@dataclass(frozen=True)
class DeliveryOutcome:
    """回覆實際送出的形式：voice（含公開音檔 URL）或 text。"""

    kind: str
    audio_url: str = ""


class VoiceReplyDelivery:
    """把 TtsResult 發成 LINE 回覆：有音檔→上傳→語音（可附文字）；否則→文字泡泡。
    上傳或語音回覆失敗一律退回文字，絕不讓回覆消失。
    show_transcript：debug 用，在文字泡泡最前面附上本輪 ASR 辨識到的長者原話
    （只進文字泡泡、不進語音合成）。"""

    def __init__(self, publisher, include_text: bool, show_transcript: bool = False) -> None:
        self._publisher = publisher
        self._include_text = include_text
        self._show_transcript = show_transcript

    def _compose_text(self, result: TtsResult, *, include_reply: bool) -> str | None:
        # debug 模式：「辨識：…」空一行「回復：…」；非 debug 就只回覆文字。
        if self._show_transcript and result.transcript:
            parts = [f"辨識：{result.transcript}"]
            if include_reply:
                parts.append(f"回復：{result.text}")
            return "\n\n".join(parts)
        return result.text if include_reply else None

    def deliver(self, msg: InboundMessage, result: TtsResult) -> DeliveryOutcome:
        if result.audio is None or self._publisher is None or msg.reply_voice is None:
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")
        try:
            url = self._publisher.publish(result.audio, content_type="audio/mp4")
            text = self._compose_text(result, include_reply=self._include_text)
            msg.reply_voice(url, result.duration_ms, text)
            return DeliveryOutcome(kind="voice", audio_url=url)
        except Exception:  # noqa: BLE001 - 任何失敗都退回文字
            logger.warning("語音回覆失敗，退回文字泡泡")
            msg.reply(self._compose_text(result, include_reply=True) or result.text)
            return DeliveryOutcome(kind="text")


def dispatch(
    msg: InboundMessage,
    *,
    pipeline,
    binding,
    gate,
    voice=None,
    traces: TraceStore | None = None,
    text_input_enabled: bool = False,
    timer: Callable[[], float] = time.monotonic,
) -> None:
    if msg.kind == "text":
        reply = binding.handle(msg.line_user_id, msg.text)
        if reply is not None:
            msg.reply(reply)
            return
        # 非綁定自由文字：旗標關維持只收語音；旗標開才轉進對話管線（Debug）。
        if not text_input_enabled:
            msg.reply(NON_AUDIO_PROMPT)
            return
        elder_id = gate.resolve_elder(msg.line_user_id)
        if elder_id is None:
            msg.reply(BIND_FIRST_PROMPT)
            return
        _run_pipeline(
            msg,
            lambda: pipeline.process_text(
                msg.text,
                elder_id=elder_id,
                line_user_id=msg.line_user_id,
                trace_id=msg.trace_id,
            ),
            voice=voice,
            traces=traces,
            timer=timer,
        )
        return
    if msg.kind != "audio":
        msg.reply(NON_AUDIO_PROMPT)
        return
    elder_id = gate.resolve_elder(msg.line_user_id)
    if elder_id is None:
        msg.reply(BIND_FIRST_PROMPT)
        return
    _run_pipeline(
        msg,
        lambda: pipeline.process(
            msg.audio,
            elder_id=elder_id,
            line_user_id=msg.line_user_id,
            trace_id=msg.trace_id,
            audio_url=msg.audio_url,
        ),
        voice=voice,
        traces=traces,
        timer=timer,
    )


def _run_pipeline(
    msg: InboundMessage,
    produce: Callable[[], TtsResult],
    *,
    voice,
    traces: TraceStore | None,
    timer: Callable[[], float],
) -> None:
    """執行對話管線並發送回覆：語音與文字共用。任一階段失敗回退提示。"""
    try:
        result = produce()
    except (ASRError, LLMError, MemoryError) as exc:
        logger.warning("對話管線失敗（回退提示）：%s: %s", type(exc).__name__, exc)
        msg.reply(FALLBACK_PROMPT)
        return
    started = timer()
    if voice is not None:
        # 「or」容忍測試替身回 None（既有 _SpyVoice 類 fake）。
        outcome = voice.deliver(msg, result) or DeliveryOutcome(kind="text")
    else:
        msg.reply(result.text)
        outcome = DeliveryOutcome(kind="text")
    _record_reply(traces, msg, outcome, started, timer)


def _record_reply(
    traces: TraceStore | None,
    msg: InboundMessage,
    outcome: DeliveryOutcome,
    started: float,
    timer: Callable[[], float],
) -> None:
    if traces is None or not msg.trace_id:
        return
    latency_ms = int((timer() - started) * 1000)
    safe_record(
        lambda: traces.record_reply(
            trace_id=msg.trace_id,
            line_user_id=msg.line_user_id,
            kind=outcome.kind,
            status="ok",
            latency_ms=latency_ms,
            audio_url=outcome.audio_url,
        )
    )
