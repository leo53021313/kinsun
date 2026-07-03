"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理；各階段觀測埋點。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace

from kinsun.agent import CareAgent
from kinsun.observability.store import TraceStore, safe_record
from kinsun.safety.detector import RiskDetector
from kinsun.safety.events import RiskEventStore
from kinsun.safety.notifier import Notifier
from kinsun.safety.tiers import RiskTier
from kinsun.speech.asr import ASRClient
from kinsun.speech.tts import TTSClient, TTSError, TtsResult

logger = logging.getLogger("kinsun.pipeline")


class VoicePipeline:
    def __init__(
        self,
        *,
        asr: ASRClient,
        agent: CareAgent,
        tts: TTSClient,
        detector: RiskDetector,
        notifier: Notifier,
        risk_events: RiskEventStore,
        traces: TraceStore | None = None,
        model_name: str = "",
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._asr = asr
        self._agent = agent
        self._tts = tts
        self._detector = detector
        self._notifier = notifier
        self._risk_events = risk_events
        self._traces = traces
        self._model_name = model_name
        self._timer = timer

    def process(
        self,
        audio: bytes,
        *,
        line_user_id: str,
        content_type: str = "audio/m4a",
        trace_id: str = "",
        audio_url: str = "",
    ) -> TtsResult:
        user_text = self._transcribe(
            audio,
            content_type=content_type,
            line_user_id=line_user_id,
            trace_id=trace_id,
            audio_url=audio_url,
        )
        assessment = self._detector.assess(user_text)
        # 危急通知須獨立於回覆生成：先落庫＋通知家屬，才產生回覆。
        # 否則 agent 生成回覆時若丟例外，會讓已偵測到的危急漏通知。
        if assessment.tier >= RiskTier.L2:
            try:
                self._risk_events.record(line_user_id, assessment, trace_id=trace_id or None)
            except Exception:  # noqa: BLE001 - 落庫失敗不可中斷對話
                logger.warning("危急事件落庫失敗")
            self._notifier.notify(line_user_id, assessment)
        reply_text = self._generate(line_user_id, user_text, trace_id=trace_id)
        result = self._synthesize(reply_text, line_user_id=line_user_id, trace_id=trace_id)
        # 附上本輪辨識到的長者原話（供 VoiceReplyDelivery 在 debug 模式回傳）。
        return replace(result, transcript=user_text)

    def _latency_ms(self, started: float) -> int:
        return int((self._timer() - started) * 1000)

    def _transcribe(
        self,
        audio: bytes,
        *,
        content_type: str,
        line_user_id: str,
        trace_id: str,
        audio_url: str,
    ) -> str:
        started = self._timer()
        try:
            text = self._asr.transcribe(audio, content_type=content_type)
        except Exception as exc:
            self._record_asr(
                trace_id,
                line_user_id,
                "error",
                started,
                "",
                audio_url,
                f"{type(exc).__name__}: {exc}",
            )
            raise
        self._record_asr(trace_id, line_user_id, "ok", started, text, audio_url, "")
        return text

    def _record_asr(
        self,
        trace_id: str,
        line_user_id: str,
        status: str,
        started: float,
        transcript: str,
        audio_url: str,
        error_message: str,
    ) -> None:
        if self._traces is None:
            return
        traces = self._traces
        latency_ms = self._latency_ms(started)
        safe_record(
            lambda: traces.record_asr_call(
                trace_id=trace_id,
                line_user_id=line_user_id,
                status=status,
                latency_ms=latency_ms,
                transcript=transcript,
                source_audio_url=audio_url,
                error_message=error_message,
            )
        )

    def _generate(self, line_user_id: str, user_text: str, *, trace_id: str) -> str:
        started = self._timer()
        try:
            reply = self._agent.handle(line_user_id, user_text)
        except Exception as exc:
            self._record_llm(
                trace_id, line_user_id, "error", started, "", f"{type(exc).__name__}: {exc}"
            )
            raise
        self._record_llm(trace_id, line_user_id, "ok", started, reply, "")
        return reply

    def _record_llm(
        self,
        trace_id: str,
        line_user_id: str,
        status: str,
        started: float,
        content: str,
        error_message: str,
    ) -> None:
        # 現階段每輪記一筆（涵蓋整個 agent 含工具迴圈）；token 由 Gemini usage
        # 尚未透出，先記 NULL——見規格「未來工作」。
        if self._traces is None:
            return
        traces = self._traces
        latency_ms = self._latency_ms(started)
        safe_record(
            lambda: traces.record_llm_call(
                trace_id=trace_id,
                line_user_id=line_user_id,
                status=status,
                latency_ms=latency_ms,
                model_name=self._model_name,
                input_tokens=None,
                output_tokens=None,
                content=content,
                error_message=error_message,
            )
        )

    def _synthesize(self, reply_text: str, *, line_user_id: str, trace_id: str) -> TtsResult:
        started = self._timer()
        try:
            result = self._tts.synthesize(reply_text)
        except TTSError as exc:
            logger.warning("TTS 合成失敗，退化為純文字回覆")
            self._record_tts(
                trace_id, line_user_id, "error", started, reply_text, f"{type(exc).__name__}: {exc}"
            )
            return TtsResult(text=reply_text, audio=None)
        self._record_tts(trace_id, line_user_id, "ok", started, reply_text, "")
        return result

    def _record_tts(
        self,
        trace_id: str,
        line_user_id: str,
        status: str,
        started: float,
        content: str,
        error_message: str,
    ) -> None:
        if self._traces is None:
            return
        traces = self._traces
        latency_ms = self._latency_ms(started)
        safe_record(
            lambda: traces.record_tts_call(
                trace_id=trace_id,
                line_user_id=line_user_id,
                status=status,
                latency_ms=latency_ms,
                content=content,
                error_message=error_message,
            )
        )
