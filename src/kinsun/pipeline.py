"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理；各階段觀測埋點。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import replace

from kinsun import background, tracing, turn_context
from kinsun.agent import NOT_HEARD_REPLY, CareAgent
from kinsun.llm import LLMUsage, collect_llm_usage
from kinsun.logging_setup import log_trace
from kinsun.observability.models import (
    LLM_CALL_KIND_AGENT,
    LLM_CALL_KIND_MODERATION,
    LLM_CALL_KIND_RISK_CLASSIFY,
)
from kinsun.observability.store import TraceStore, safe_record
from kinsun.reports.reminders import ReminderLogStore
from kinsun.safety.detector import RiskDetector
from kinsun.safety.events import RiskEventStore
from kinsun.safety.moderation import AbuseModerator, ModerationResult, reply_for
from kinsun.safety.notifier import Notifier
from kinsun.safety.tiers import RiskAssessment, RiskTier
from kinsun.speech.asr import ASRClient
from kinsun.speech.chunking import split_for_speech
from kinsun.speech.tts import TTSClient, TTSError, TtsResult, VoiceReference
from kinsun.voice_profiles.store import VoiceProfileStore

logger = logging.getLogger("kinsun.pipeline")


def _has_recognizable_speech(text: str) -> bool:
    """辨識結果是否含可辨識語音（任一字母／數字／漢字）。

    Whisper 系 ASR 對近無聲的極短音檔會確定性幻覺出純標點（實錄「? ? ?」）：去掉
    標點與空白後為空，內容上等同空辨識，故與空字串一併走回退話術，不進分級與 agent。
    """
    return any(char.isalnum() for char in text)


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
        moderator: AbuseModerator | None = None,
        voice_profiles: VoiceProfileStore | None = None,
        chunked_channels: frozenset[str] = frozenset(),
        turn_budget_seconds: float = 0.0,
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
        # 選填（預設 None＝所有長輩皆用 DGX 端全域預設聲音）：長輩客製化聲音複製
        # （2026-07-30），未設定時不影響既有呼叫端與測試。
        self._voice_profiles = voice_profiles
        self._response_window_seconds = response_window_seconds
        # 選填（預設 None＝不審核，等同 SAFETY_MODERATION_ENABLED=false）。
        self._moderator = moderator
        # 啟用 TTS 分段串流的通道（2026-07-26 延遲優化）。預設空集合＝所有通道維持
        # 原行為（整段合成）。逐通道而非全域開關，是因為分段需要**投遞端配合**：
        # App 拿得到段數、會逐段拉並接著播；LINE 只能收一則語音訊息，給它第一句
        # 等於把後面的話吞掉。故 app.py 只把 "app" 放進來。
        self._chunked_channels = chunked_channels
        # 這一輪從長輩開口到必須交出回覆的總時間（秒）；0＝不限制，回到逐次逾時的
        # 舊行為。⚠️ 它管的是**相加**：一輪會依序打三次 Gemini（分級→審核→生成），
        # 各自的 30 秒逾時攔得住一次呼叫，攔不住三次疊起來——2026-07-28 Gemini 3.5
        # 過載那晚，三次各卡滿 30 秒，長輩等了 96.6 秒才聽到回退話術。
        self._turn_budget_seconds = turn_budget_seconds

    def _budgeted(self):
        """本輪的預算範圍；未設定（0）時回不做事的空範圍。

        ⚠️ 預算從**收到長輩的音檔**就開始跑，ASR 也算在裡面：長輩等的是「按完到聽見」，
        不是「模型開工到聽見」。把 ASR 排除在外會讓上限說的 30 秒實際變成 37 秒。
        """
        if self._turn_budget_seconds <= 0:
            return nullcontext()
        return turn_context.turn_budget(self._turn_budget_seconds)

    @tracing.track(
        name="care_turn_voice",
        type="general",
        capture_input=True,
        capture_output=False,  # 回傳 TtsResult 含音檔 bytes
        ignore_arguments=["audio"],
    )
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
        tracing.tag_current_trace(trace_id=trace_id, channel=channel, elder_id=elder_id)
        # 本輪的 log 全部蓋上 trace_id（2026-07-27）：logs 只記「發生什麼事」，
        # 內容去 Opik 看，trace_id 是兩邊之間唯一的橋。
        with log_trace(trace_id), self._budgeted():
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

    # 輸出維持關閉：回傳 TtsResult 含音檔 bytes。
    @tracing.track(name="care_turn_text", type="general", capture_input=True, capture_output=False)
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
        tracing.tag_current_trace(trace_id=trace_id, channel=channel, elder_id=elder_id)
        with log_trace(trace_id), self._budgeted():
            return self._process_transcribed(
                text, elder_id=elder_id, external_id=external_id, channel=channel, trace_id=trace_id
            )

    def _process_transcribed(
        self, user_text: str, *, elder_id: str, external_id: str, channel: str, trace_id: str
    ) -> TtsResult:
        """會話鍵為 elder_id；external_id＋channel 僅供觀測五表標記（可為空字串）。"""
        # 空輸入守門（2026-07-18）：靜音誤觸的 ASR 辨識為空、或幻覺出純標點（Whisper 系
        # 對近無聲短檔的確定性幻覺，實錄「? ? ?」），去標點後皆無內容可分級、可回應也不
        # 該進記憶，直接以回退話術（仍走 TTS）請長輩再說一次。
        if not _has_recognizable_speech(user_text):
            # ⚠️ 這是唯一真的「沒聽清楚」的情形，故用 NOT_HEARD_REPLY 而非系統故障話術：
            # 這裡叫長輩再說一次是對的（他再說一次真的會成功）。其他回退點都是我們自己
            # 壞掉，叫他重試只會讓他一再失敗（2026-07-26 實測 M4）。
            tracing.update_trace_metadata(fallback="empty_speech")
            tracing.set_current_trace_io(user_input=user_text, assistant_output=NOT_HEARD_REPLY)
            result = self._synthesize(
                NOT_HEARD_REPLY,
                elder_id=elder_id,
                external_id=external_id,
                channel=channel,
                trace_id=trace_id,
            )
            return replace(result, transcript=user_text)
        # 情境組裝先行啟動（2026-07-26 延遲實測）：它是本輪最慢的一段（長期記憶檢索
        # ＋七次事實查詢，約 2.9 秒），而輸入只有 elder_id＋原話，不必等安全檢查跑完。
        # ⚠️ 這只改「何時開始組」，**決策順序一字未動**——底下的落庫／通報／攔截先後
        # 完全照舊。prepare 只讀不寫，故被攔的那一輪雖白做一次組裝，仍不會進記憶。
        prepared = self._agent.prepare(elder_id, user_text)
        assessment = self._assess(
            user_text, external_id=external_id, channel=channel, trace_id=trace_id
        )
        tracing.update_trace_metadata(risk_tier=assessment.tier.name)
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
            # 通知文案引長輩原話（2026-07-29 Leo 定案），故把 user_text 一併交給通知端。
            self._notifier.notify(elder_id, assessment, user_text)
        # ⚠️ 位置有意義，請勿上移：反思的觀測訊號絕不可排在家屬通報之前（見
        # _mark_reminder_responded 的 docstring）。語音（process）與文字（process_text）
        # 都流經此處，故標記一次即涵蓋兩條路徑。
        self._mark_reminder_responded(elder_id)
        # 濫用審核（2026-07-25）：⚠️ 位置有意義，請勿上移——必須排在危急落庫與家屬
        # 通報之後。攔截會整段跳過 agent，若排在前面，一句被誤判的「我不想活了」就會
        # 讓 risk_events 不落庫、家屬永遠收不到 L2 通知（那句話是 classify_keywords
        # 必定判 L2 的求死意念）。順序由 test_pipeline 的
        # test_moderation_runs_after_family_notification 守住。
        # 被攔的這一輪刻意不寫進記憶（記憶只由 agent.handle 寫）：綁架企圖不該變成
        # 明天的對話脈絡，也不該進長期記憶。
        if self._moderator is not None:
            moderation = self._moderate(
                user_text, external_id=external_id, channel=channel, trace_id=trace_id
            )
            if moderation.is_blocked:
                tracing.update_trace_metadata(moderation=moderation.category.value)
                blocked_reply = reply_for(moderation.category)
                tracing.set_current_trace_io(user_input=user_text, assistant_output=blocked_reply)
                result = self._synthesize(
                    blocked_reply,
                    elder_id=elder_id,
                    external_id=external_id,
                    channel=channel,
                    trace_id=trace_id,
                )
                return replace(result, transcript=user_text)
        reply_text = self._generate(
            elder_id,
            user_text,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
            has_risk_signal=assessment.tier >= RiskTier.L1,
            prepared=prepared,
        )
        # 對話原話＋回覆寫進 trace I/O，Opik Threads 才顯示 First／Last message。
        tracing.set_current_trace_io(user_input=user_text, assistant_output=reply_text)
        result = self._synthesize(
            reply_text,
            elder_id=elder_id,
            external_id=external_id,
            channel=channel,
            trace_id=trace_id,
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
        now 在**提交前**取值，不可搬進背景動作裡：時間窗判定的基準是長輩開口的那一刻，
        不是背景執行緒剛好排到的那一刻。

        UPDATE 本身走 `background.run`（2026-07-26 延遲實測）：它是一次約 0.21 秒的
        Supabase 跨網往返，而反思的訊號沒有任何人在等——移出回覆路徑後，上面那段
        「try/except 擋得住錯誤、擋不住延遲」的疑慮也就徹底消失了。
        """
        if self._reminder_logs is None:
            return
        reminder_logs = self._reminder_logs
        now = time.time()
        within_seconds = self._response_window_seconds

        def mark() -> None:
            try:
                reminder_logs.mark_responded(elder_id, now=now, within_seconds=within_seconds)
            except Exception:  # noqa: BLE001 - 訊號落庫失敗不可中斷對話
                logger.warning("提醒回應標記失敗 elder=%s", elder_id)

        background.run(mark)

    def _latency_ms(self, started: float) -> int:
        return int((self._timer() - started) * 1000)

    @tracing.track(name="risk_assess", type="general", capture_input=True, capture_output=True)
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
                    kind=LLM_CALL_KIND_RISK_CLASSIFY,
                )
            )
        return assessment

    @tracing.track(name="abuse_moderate", type="general", capture_input=True, capture_output=True)
    def _moderate(
        self, user_text: str, *, external_id: str, channel: str, trace_id: str
    ) -> ModerationResult:
        """濫用審核也納入觀測（比照 _assess）：token 進收集器、每輪補一筆 llm_call。

        moderator.moderate 從不拋例外（fail-open），故錯誤以 llm:error 訊號辨識，
        不能沿用 _span 的例外偵測。模型名沿用 safety_model_name——審核與危急分級
        共用同一顆 safety 模型（見 app.py 的 safety_llm）。

        前置條件：`self._moderator` 不為 None，由唯一呼叫端 `_process_transcribed`
        守門——審核未啟用時整段不進來，才不會平白產生一個空 span。
        """
        usage = LLMUsage()
        started = self._timer()
        with collect_llm_usage(usage):
            moderation = self._moderator.moderate(user_text)
        if self._traces is not None:
            traces = self._traces
            latency_ms = self._latency_ms(started)
            is_error = "llm:error" in moderation.signals
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
                    content=f"濫用審核 {moderation.category.value}：{moderation.reason}",
                    error_message="審核器故障（fail-open 放行）" if is_error else "",
                    kind=LLM_CALL_KIND_MODERATION,
                )
            )
        return moderation

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

    @tracing.track(
        name="asr",
        type="general",
        capture_input=True,
        capture_output=True,
        ignore_arguments=["audio"],  # 整包音檔 bytes，塞進 span 只會讓它讀不動
    )
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

    @tracing.track(
        name="agent_generate",
        type="llm",
        capture_input=True,
        capture_output=True,
        ignore_arguments=["prepared"],  # PreparedTurn 物件，序列化沒有意義
    )
    def _generate(
        self,
        elder_id: str,
        user_text: str,
        *,
        external_id: str,
        channel: str,
        trace_id: str,
        has_risk_signal: bool,
        prepared=None,
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
                kind=LLM_CALL_KIND_AGENT,
            )
        ):
            with collect_llm_usage(usage):
                reply = self._agent.handle(
                    elder_id,
                    user_text,
                    trace_id=trace_id,
                    has_risk_signal=has_risk_signal,
                    prepared=prepared,
                )
        return reply

    # 輸出維持關閉：回傳 TtsResult 含音檔 bytes；輸入（要唸的文字）才是要看的東西。
    @tracing.track(name="tts", type="general", capture_input=True, capture_output=False)
    def _synthesize(
        self, reply_text: str, *, elder_id: str, external_id: str, channel: str, trace_id: str
    ) -> TtsResult:
        """啟用分段的通道只合成**第一段**，其餘由投遞端逐段取（2026-07-26 延遲優化）。

        回傳的 `text` 一律是完整回覆——長輩看到的字幕、寫進記憶的內容、觀測留存的
        內容都不可以因為分段而被切掉；只有 `audio` 是第一段。切不出兩段以上時
        （短回覆、回退話術、被攔的回絕話術）不分段，因為分段的代價（多一次往返）
        換不到任何東西。分段與長輩客製化聲音（2026-07-30）彼此獨立、可同時生效。
        """
        voice = self._resolve_voice(elder_id)
        chunks = split_for_speech(reply_text) if channel in self._chunked_channels else []
        chunked = len(chunks) > 1
        spoken = chunks[0] if chunked else reply_text
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
                result = self._tts.synthesize(spoken, voice=voice)
                return replace(result, text=reply_text, chunk_count=len(chunks) if chunked else 0)
        except TTSError:
            logger.warning("TTS 合成失敗，退化為純文字回覆")
            return TtsResult(text=reply_text, audio=None)

    def _resolve_voice(self, elder_id: str) -> VoiceReference | None:
        """長輩客製化聲音複製（2026-07-30）：無設定檔或未設 voice_profiles 則回 None
        （TTSClient 沿用 DGX 端全域預設聲音）。"""
        if self._voice_profiles is None:
            return None
        profile = self._voice_profiles.get_active(elder_id)
        if profile is None:
            return None
        return VoiceReference(
            elder_id=profile.elder_id,
            prompt_audio_url=profile.prompt_audio_url,
            prompt_text=profile.prompt_text,
        )
