"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理；各階段觀測埋點。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
        elder_id: str,
        line_user_id: str = "",
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
        return self._process_transcribed(
            user_text, elder_id=elder_id, line_user_id=line_user_id, trace_id=trace_id
        )

    def process_text(
        self, text: str, *, elder_id: str, line_user_id: str = "", trace_id: str = ""
    ) -> TtsResult:
        """文字輸入路徑（✅ D-11 正式）：跳過 ASR，其餘與語音同管線（危急偵測＋回覆＋記憶）。"""
        return self._process_transcribed(
            text, elder_id=elder_id, line_user_id=line_user_id, trace_id=trace_id
        )

    def _process_transcribed(
        self, user_text: str, *, elder_id: str, line_user_id: str, trace_id: str
    ) -> TtsResult:
        """會話鍵為 elder_id；line_user_id 僅供觀測五表標記（可為空字串）。"""
        assessment = self._detector.assess(user_text)
        # 危急通知須獨立於回覆生成：先落庫＋通知家屬，才產生回覆。
        # 否則 agent 生成回覆時若丟例外，會讓已偵測到的危急漏通知。
        if assessment.tier >= RiskTier.L2:
            try:
                self._risk_events.record(elder_id, assessment, trace_id=trace_id or None)
            except Exception:  # noqa: BLE001 - 落庫失敗不可中斷對話
                logger.warning("危急事件落庫失敗")
            self._notifier.notify(elder_id, assessment)
        reply_text = self._generate(
            elder_id, user_text, line_user_id=line_user_id, trace_id=trace_id
        )
        result = self._synthesize(reply_text, line_user_id=line_user_id, trace_id=trace_id)
        # 附上本輪的使用者原話（語音為 ASR 辨識、文字為輸入），供 debug 顯示。
        return replace(result, transcript=user_text)

    def _latency_ms(self, started: float) -> int:
        return int((self._timer() - started) * 1000)

    @contextmanager
    def _span(self, record: Callable[[TraceStore, str, int, str], object]) -> Iterator[None]:
        """量測一個 stage 並記一筆 trace（成功或失敗），是三個階段共用的觀測 seam。

        record 為記錄建構器：拿到 (traces, status, latency_ms, error_message) 後呼叫對應的
        record_*_call；結果相依欄位（如 transcript／content）由呼叫端以 closure 抓區域變數帶入。
        traces 為 None 時整段 no-op；記錄以 safe_record 包裹，觀測失敗不影響對話。
        例外照原樣往外拋（tts 的退回文字由呼叫端在 with 外自行接住）。
        """
        started = self._timer()
        status, error_message = "ok", ""
        try:
            yield
        except Exception as exc:
            status, error_message = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self._traces is not None:
                traces = self._traces
                latency_ms = self._latency_ms(started)
                safe_record(lambda: record(traces, status, latency_ms, error_message))

    def _transcribe(
        self,
        audio: bytes,
        *,
        content_type: str,
        line_user_id: str,
        trace_id: str,
        audio_url: str,
    ) -> str:
        text = ""
        with self._span(
            lambda traces, status, latency_ms, error_message: traces.record_asr_call(
                trace_id=trace_id,
                line_user_id=line_user_id,
                status=status,
                latency_ms=latency_ms,
                transcript=text,
                source_audio_url=audio_url,
                error_message=error_message,
            )
        ):
            text = self._asr.transcribe(audio, content_type=content_type)
        return text

    def _generate(self, elder_id: str, user_text: str, *, line_user_id: str, trace_id: str) -> str:
        # 現階段每輪記一筆（涵蓋整個 agent 含工具迴圈）；token 由 Gemini usage
        # 尚未透出，先記 NULL——見規格「未來工作」。
        reply = ""
        with self._span(
            lambda traces, status, latency_ms, error_message: traces.record_llm_call(
                trace_id=trace_id,
                line_user_id=line_user_id,
                status=status,
                latency_ms=latency_ms,
                model_name=self._model_name,
                input_tokens=None,
                output_tokens=None,
                content=reply,
                error_message=error_message,
            )
        ):
            reply = self._agent.handle(elder_id, user_text)
        return reply

    def _synthesize(self, reply_text: str, *, line_user_id: str, trace_id: str) -> TtsResult:
        try:
            with self._span(
                lambda traces, status, latency_ms, error_message: traces.record_tts_call(
                    trace_id=trace_id,
                    line_user_id=line_user_id,
                    status=status,
                    latency_ms=latency_ms,
                    content=reply_text,
                    error_message=error_message,
                )
            ):
                return self._tts.synthesize(reply_text)
        except TTSError:
            logger.warning("TTS 合成失敗，退化為純文字回覆")
            return TtsResult(text=reply_text, audio=None)
