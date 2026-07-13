"""通道中立的入站訊息與分派（不依賴任何特定通道 SDK）。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from kinsun.accounts.models import Channel
from kinsun.agent import FALLBACK_REPLY
from kinsun.llm import LLMError
from kinsun.memory.shortterm import MemoryStoreError
from kinsun.observability.store import TraceStore, safe_record
from kinsun.speech.asr import ASRError
from kinsun.speech.tts import TtsResult

logger = logging.getLogger("kinsun.inbound")

NON_AUDIO_PROMPT = "金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
# 回退話術與 agent 層共用單一出處（✅ 庚-37：FALLBACK_PROMPT／FALLBACK_REPLY 合併）。
FALLBACK_PROMPT = FALLBACK_REPLY
BIND_FIRST_PROMPT = (
    "金孫需要先完成綁定才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


@dataclass(frozen=True)
class InboundMessage:
    """通道中立的入站訊息。kind ∈ text/audio/other；reply 為綁定好的回覆 handle，
    reply_voice 為語音回覆 handle（url、duration_ms、text）。
    channel＋external_id 為來源通道與其帳號識別（如 LINE userId），分派時解析成本人。
    trace_id／audio_url 供觀測鏈路與音檔回放（無觀測時為空字串）。
    received_at 為通道收件時刻的單調時鐘值（與 dispatch 的 timer 同源，✅ D-05 戊-2
    往返延遲起點）；0＝未知，該輪 round_trip_ms 記 NULL。"""

    channel: Channel
    external_id: str
    kind: str
    text: str
    audio: bytes
    reply: Callable[[str], None]
    reply_voice: Callable[[str, int, str | None], None] | None = None
    trace_id: str = ""
    audio_url: str = ""
    received_at: float = 0.0


@dataclass(frozen=True)
class DeliveryOutcome:
    """回覆實際送出的形式：voice（含公開音檔 URL）或 text。"""

    kind: str
    audio_url: str = ""


class VoiceReplyDelivery:
    """把 TtsResult 發成回覆（通道中立，✅ 庚-37）：有音檔→上傳→語音（可附文字）；
    否則→文字泡泡。
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
    text_input_enabled: bool = True,
    timer: Callable[[], float] = time.monotonic,
    elder_id: str | None = None,
) -> None:
    """elder_id：呼叫端已解析過本人時傳入（✅ 庚-12），dispatch 不再重查閘門；
    未傳（LINE webhook 路徑）照舊經 gate 解析。"""
    if msg.kind == "text":
        reply = binding.handle(msg.external_id, msg.text)
        if reply is not None:
            msg.reply(reply)
            return
        # 非綁定自由文字走完整對話管線（危急偵測＋回覆＋記憶，✅ D-11 與語音同等對待）；
        # 旗標關為維運逃生口，回到只收語音提示。
        if not text_input_enabled:
            msg.reply(NON_AUDIO_PROMPT)
            return
        elder_id = elder_id or gate.resolve_elder(msg.channel, msg.external_id)
        if elder_id is None:
            msg.reply(BIND_FIRST_PROMPT)
            return
        _run_pipeline(
            msg,
            lambda: pipeline.process_text(
                msg.text,
                elder_id=elder_id,
                external_id=msg.external_id,
                channel=msg.channel.value,
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
    elder_id = elder_id or gate.resolve_elder(msg.channel, msg.external_id)
    if elder_id is None:
        msg.reply(BIND_FIRST_PROMPT)
        return
    _run_pipeline(
        msg,
        lambda: pipeline.process(
            msg.audio,
            elder_id=elder_id,
            external_id=msg.external_id,
            channel=msg.channel.value,
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
    except (ASRError, LLMError, MemoryStoreError) as exc:
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
    ended = timer()
    latency_ms = int((ended - started) * 1000)
    # 往返延遲（✅ D-05 戊-2）：通道收件 → 回覆送達的端到端耗時；起點未知記 NULL。
    round_trip_ms = int((ended - msg.received_at) * 1000) if msg.received_at else None
    safe_record(
        lambda: traces.record_reply(
            trace_id=msg.trace_id,
            external_id=msg.external_id,
            channel=msg.channel.value,
            kind=outcome.kind,
            status="ok",
            latency_ms=latency_ms,
            round_trip_ms=round_trip_ms,
            audio_url=outcome.audio_url,
        )
    )
