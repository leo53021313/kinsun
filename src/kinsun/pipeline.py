"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理；各階段觀測埋點。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace

from kinsun.agent import FALLBACK_REPLY, CareAgent
from kinsun.llm import LLMUsage, collect_llm_usage
from kinsun.observability.store import TraceStore, safe_record
from kinsun.reports.reminders import ReminderLogStore
from kinsun.safety.detector import RiskDetector
from kinsun.safety.events import RiskEventStore
from kinsun.safety.notifier import Notifier
from kinsun.safety.tiers import RiskAssessment, RiskTier
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
        safety_model_name: str = "",
        timer: Callable[[], float] = time.monotonic,
        reminder_logs: ReminderLogStore | None = None,
        response_window_seconds: int = 3600,
    ) -> None:
        self._asr = asr
        self._agent = agent
        self._tts = tts
        self._detector = detector
        self._notifier = notifier
        self._risk_events = risk_events
        self._traces = traces
        self._model_name = model_name
        self._safety_model_name = safety_model_name
        self._timer = timer
        # 選填（預設 None＝不標記）：既有呼叫端與測試不受影響。
        self._reminder_logs = reminder_logs
        self._response_window_seconds = response_window_seconds

    def process(
        self,
        audio: bytes,
        *,
        elder_id: str,
        external_id: str = "",
        channel: str = "",
        content_type: str = "audio/m4a",
        trace_id: str = "",
        audio_url: str = "",
    ) -> TtsResult:
        user_text = self._transcribe(
            audio,
            content_type=content_type,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
            audio_url=audio_url,
        )
        return self._process_transcribed(
            user_text,
            elder_id=elder_id,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
        )

    def process_text(
        self,
        text: str,
        *,
        elder_id: str,
        external_id: str = "",
        channel: str = "",
        trace_id: str = "",
    ) -> TtsResult:
        """文字輸入路徑（✅ D-11 正式）：跳過 ASR，其餘與語音同管線（危急偵測＋回覆＋記憶）。"""
        return self._process_transcribed(
            text, elder_id=elder_id, external_id=external_id, channel=channel, trace_id=trace_id
        )

    def _process_transcribed(
        self, user_text: str, *, elder_id: str, external_id: str, channel: str, trace_id: str
    ) -> TtsResult:
        """會話鍵為 elder_id；external_id＋channel 僅供觀測五表標記（可為空字串）。"""
        # 空輸入守門（2026-07-18）：靜音誤觸的 ASR 辨識為空，沒有內容可分級、
        # 可回應也不該進記憶，直接以回退話術（仍走 TTS）請長輩再說一次。
        if not user_text.strip():
            result = self._synthesize(
                FALLBACK_REPLY, external_id=external_id, channel=channel, trace_id=trace_id
            )
            return replace(result, transcript=user_text)
        assessment = self._assess(
            user_text, external_id=external_id, channel=channel, trace_id=trace_id
        )
        # 危急通知須獨立於回覆生成：先落庫＋通知家屬，才產生回覆。
        # 否則 agent 生成回覆時若丟例外，會讓已偵測到的危急漏通知。
        # 落庫門檻＝L1：一般 L1（小訊號）是每日摘要的資料來源（✅ D-10 己-5，庚-01），
        # fail-safe L1（✅ D-31）留痕供 admin 告警——兩者都只落庫、不通知；通知門檻維持 L2。
        if assessment.tier >= RiskTier.L1:
            try:
                self._risk_events.record(elder_id, assessment, trace_id=trace_id or None)
            except Exception:  # noqa: BLE001 - 落庫失敗不可中斷對話
                logger.warning("危急事件落庫失敗")
        if assessment.tier >= RiskTier.L2:
            self._notifier.notify(elder_id, assessment)
        # ⚠️ 位置有意義，請勿上移：反思的觀測訊號絕不可排在家屬通報之前（見
        # _mark_reminder_responded 的 docstring）。語音（process）與文字（process_text）
        # 都流經此處，故標記一次即涵蓋兩條路徑。
        self._mark_reminder_responded(elder_id)
        reply_text = self._generate(
            elder_id, user_text, external_id=external_id, channel=channel, trace_id=trace_id
        )
        result = self._synthesize(
            reply_text, external_id=external_id, channel=channel, trace_id=trace_id
        )
        # 附上本輪的使用者原話（語音為 ASR 辨識、文字為輸入），供 debug 顯示。
        return replace(result, transcript=user_text)

    def _mark_reminder_responded(self, elder_id: str) -> None:
        """長輩開口＝可能在回應剛推的提醒（時間窗判定，不做內容比對）。

        這是反思的行為訊號來源；標記失敗不可影響對話。

        ⚠️ 呼叫點必須排在危急落庫＋家屬通報**之後**，不可上移到本輪開頭。下方的
        try/except 擋得住這個 UPDATE 的**錯誤**，擋不住它的**延遲**：全庫沒有任何
        statement_timeout／lock_timeout，撞到鎖就是無限期阻塞。部署時 `ensure_schema`
        以非 CONCURRENTLY 方式建 reminder_logs 的索引，對該表持 ShareLock、擋住所有
        寫入；若此時長輩傳來「我喘不過氣」，而標記排在通報之前，家屬通報就會跟著卡在
        鎖上，直到索引建完。一個純粹給反思用的觀測訊號，不該擋在長輩的求救前面。
        時間窗語意與本輪中的位置無關（now 取的是牆鐘時間），故後移零成本。
        順序由 test_critical_notification_precedes_the_reminder_signal_marking 守住。

        ⚠️ now 用 time.time()（epoch 秒），不可用 self._timer——後者預設 time.monotonic，
        只能量延遲、不是牆鐘時間，拿去跟 reminder_logs.created_at 比較會得到垃圾。
        """
        if self._reminder_logs is None:
            return
        try:
            self._reminder_logs.mark_responded(
                elder_id,
                now=time.time(),
                within_seconds=self._response_window_seconds,
            )
        except Exception:  # noqa: BLE001 - 訊號落庫失敗不可中斷對話
            logger.warning("提醒回應標記失敗 elder=%s", elder_id)

    def _latency_ms(self, started: float) -> int:
        return int((self._timer() - started) * 1000)

    def _assess(
        self, user_text: str, *, external_id: str, channel: str, trace_id: str
    ) -> RiskAssessment:
        """危急分級也納入觀測（✅ 庚-10／A-9）：token 進收集器、每輪補一筆 llm_call。

        detector.assess 從不拋例外（fail-safe），故錯誤以 llm:error 訊號辨識，
        不能沿用 _span 的例外偵測。
        """
        usage = LLMUsage()
        started = self._timer()
        with collect_llm_usage(usage):
            assessment = self._detector.assess(user_text)
        if self._traces is not None:
            traces = self._traces
            latency_ms = self._latency_ms(started)
            is_error = "llm:error" in assessment.signals
            safe_record(
                lambda: traces.record_llm_call(
                    trace_id=trace_id,
                    external_id=external_id,
                    channel=channel,
                    status="error" if is_error else "ok",
                    latency_ms=latency_ms,
                    model_name=self._safety_model_name,
                    input_tokens=usage.input_tokens or None,
                    output_tokens=usage.output_tokens or None,
                    content=f"風險分級 {assessment.tier.name}：{assessment.reason}",
                    error_message="分級器故障（fail-safe 留痕）" if is_error else "",
                )
            )
        return assessment

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
        external_id: str,
        channel: str,
        trace_id: str,
        audio_url: str,
    ) -> str:
        text = ""
        with self._span(
            lambda traces, status, latency_ms, error_message: traces.record_asr_call(
                trace_id=trace_id,
                external_id=external_id,
                channel=channel,
                status=status,
                latency_ms=latency_ms,
                transcript=text,
                source_audio_url=audio_url,
                error_message=error_message,
            )
        ):
            text = self._asr.transcribe(audio, content_type=content_type)
        return text

    def _generate(
        self, elder_id: str, user_text: str, *, external_id: str, channel: str, trace_id: str
    ) -> str:
        # 每輪記一筆（涵蓋整個 agent 含工具迴圈）；token 用量由收集器彙總本輪
        # 所有 Gemini 呼叫（✅ D-05 戊-2）。零申報（假 LLM／無 usage_metadata）
        # 記 NULL＝「未量測」，與量測到 0 區隔。
        reply = ""
        usage = LLMUsage()
        with self._span(
            lambda traces, status, latency_ms, error_message: traces.record_llm_call(
                trace_id=trace_id,
                external_id=external_id,
                channel=channel,
                status=status,
                latency_ms=latency_ms,
                model_name=self._model_name,
                input_tokens=usage.input_tokens or None,
                output_tokens=usage.output_tokens or None,
                content=reply,
                error_message=error_message,
            )
        ):
            with collect_llm_usage(usage):
                reply = self._agent.handle(elder_id, user_text)
        return reply

    def _synthesize(
        self, reply_text: str, *, external_id: str, channel: str, trace_id: str
    ) -> TtsResult:
        try:
            with self._span(
                lambda traces, status, latency_ms, error_message: traces.record_tts_call(
                    trace_id=trace_id,
                    external_id=external_id,
                    channel=channel,
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
