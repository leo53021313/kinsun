import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from kinsun import background, turn_context
from kinsun.agent import NOT_HEARD_REPLY, CareAgent
from kinsun.llm import LLMError, Message, report_llm_usage
from kinsun.pipeline import VoicePipeline
from kinsun.reports.reminders import REMINDER_KIND_MEDICATION
from kinsun.safety.combined_classifier import (
    CombinedSafetyResult,
    LlmCombinedSafetyClassifier,
)
from kinsun.safety.detector import RiskDetector
from kinsun.safety.moderation import AbuseCategory, AbuseModerator, ModerationResult, reply_for
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts, TTSError, TtsResult
from tests.fakes import FakeReminderLogStore, FakeRiskEventStore, FakeTraceStore


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


class _NullCtx:
    system_suffix = ""
    history: list[Message] = []


class NullSession:
    def assemble(self, elder_id: str, query: str) -> _NullCtx:
        return _NullCtx()

    def record_turn(self, elder_id: str, *messages: Message, at=None) -> None:
        pass


class StubDetector:
    def __init__(self, tier: RiskTier) -> None:
        self._tier = tier

    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        return RiskAssessment(self._tier, 0.9, "stub", ["llm"])


class SpyNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RiskTier]] = []
        self.texts: list[str] = []

    def notify(self, elder_id: str, assessment: RiskAssessment, user_text: str) -> None:
        self.calls.append((elder_id, assessment.tier))
        self.texts.append(user_text)


def _pipeline(detector, notifier, risk_events=None, *, reminder_logs=None):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
        reminder_logs=reminder_logs,
        response_window_seconds=3600,
    )


def test_pipeline_replies_and_runs_detection():
    notifier = SpyNotifier()
    result = _pipeline(StubDetector(RiskTier.L0), notifier).process(b"\x00", elder_id="u1")
    assert result.text == "你說的是：阿公早安"
    assert notifier.calls == []


def test_pipeline_notifies_on_l2_or_above():
    notifier = SpyNotifier()
    _pipeline(StubDetector(RiskTier.L2), notifier).process(b"\x00", elder_id="u1")
    assert notifier.calls == [("u1", RiskTier.L2)]
    # 通知端拿到的是長輩原話（2026-07-29 Leo 定案：文案引原話、家屬自行判斷）。
    assert notifier.texts == ["阿公早安"]


class _BoomRiskEvents:
    def record(self, elder_id, assessment, *, trace_id=None):
        raise RuntimeError("db down")

    def list_for_elder(self, elder_id):
        return []


def test_pipeline_records_risk_event_on_l2():
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _pipeline(StubDetector(RiskTier.L2), notifier, events).process(b"\x00", elder_id="u1")
    assert [s for s, _ in events.recorded] == ["u1"]
    assert notifier.calls == [("u1", RiskTier.L2)]


def test_pipeline_does_not_record_l0():
    events = FakeRiskEventStore()
    _pipeline(StubDetector(RiskTier.L0), SpyNotifier(), events).process(b"\x00", elder_id="u1")
    assert events.recorded == []


class _BoomAgent:
    def prepare(self, elder_id, user_text):
        return None  # 情境預取不是本測試的對象；handle 收到 None 就當場組

    def handle(self, elder_id, user_text, **kwargs):
        raise RuntimeError("llm down")


class _BoomDetector:
    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        raise AssertionError("空辨識不得進風險分級")


def test_pipeline_empty_transcript_short_circuits_to_fallback():
    """ASR 辨識為空（靜音誤觸）：沒有內容可分級、可回應，不進 detector 與 agent，
    直接以回退話術請長輩再說一次；仍走 TTS，長輩才聽得到語音提示。"""
    pipeline = VoicePipeline(
        asr=MockAsrClient(""),
        agent=_BoomAgent(),  # 被呼叫即炸：斷言不進 agent
        tts=TextBubbleTts(),
        detector=_BoomDetector(),  # 被呼叫即炸：斷言不進分級
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    result = pipeline.process(b"\x00", elder_id="u1")
    assert result.text == NOT_HEARD_REPLY
    assert result.transcript == ""


def test_pipeline_punctuation_only_transcript_short_circuits_to_fallback():
    """Whisper 系 ASR 對近無聲短檔會確定性幻覺出純標點（實錄「? ? ?」）：去標點後
    無可辨識內容，等同空辨識——不進 detector 與 agent，直接回退話術。原話仍原樣保留
    在 transcript 供 debug 檢視。"""
    pipeline = VoicePipeline(
        asr=MockAsrClient(" ? ? ? ? ? ? ? ?"),
        agent=_BoomAgent(),  # 被呼叫即炸：斷言不進 agent
        tts=TextBubbleTts(),
        detector=_BoomDetector(),  # 被呼叫即炸：斷言不進分級
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    result = pipeline.process(b"\x00", elder_id="u1")
    assert result.text == NOT_HEARD_REPLY
    assert result.transcript == " ? ? ? ? ? ? ? ?"


def test_pipeline_notifies_before_reply_generation():
    """危急通知不可依賴回覆生成：agent 生成回覆丟例外時，家屬通知仍須先送出。"""
    notifier = SpyNotifier()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=_BoomAgent(),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L2),
        notifier=notifier,
        risk_events=FakeRiskEventStore(),
    )
    with pytest.raises(RuntimeError):
        pipeline.process(b"\x00", elder_id="u1")
    assert notifier.calls == [("u1", RiskTier.L2)]


def test_pipeline_record_failure_does_not_break():
    notifier = SpyNotifier()
    result = _pipeline(StubDetector(RiskTier.L2), notifier, _BoomRiskEvents()).process(
        b"\x00", elder_id="u1"
    )
    assert result.text == "你說的是：阿公早安"
    assert notifier.calls == [("u1", RiskTier.L2)]


class _BoomTts:
    def synthesize(self, text):
        raise TTSError("tts down")


def test_pipeline_tts_failure_degrades_to_text():
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=_BoomTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    result = pipeline.process(b"\x00", elder_id="u1")
    assert isinstance(result, TtsResult)
    assert result.text == "你說的是：阿公早安"
    assert result.audio is None


def test_pipeline_sets_transcript_from_asr():
    result = _pipeline(StubDetector(RiskTier.L0), SpyNotifier()).process(b"\x00", elder_id="u1")
    assert result.transcript == "阿公早安"


def test_pipeline_writes_trace_io_for_thread_view(monkeypatch):
    """對話輪次把原話＋回覆寫進 trace I/O，Opik Threads 才顯示 First／Last message。"""
    from kinsun import tracing

    calls: list[dict] = []
    monkeypatch.setattr(tracing, "set_current_trace_io", lambda **kw: calls.append(kw))
    result = _pipeline(StubDetector(RiskTier.L0), SpyNotifier()).process_text(
        "我今天很好", elder_id="u1"
    )
    assert calls == [{"user_input": "我今天很好", "assistant_output": result.text}]


def test_pipeline_writes_trace_io_on_empty_speech_fallback(monkeypatch):
    """靜音誤觸走回退話術：thread 仍顯示回覆，空原話不寫 input（由 helper 略過）。"""
    from kinsun import tracing

    calls: list[dict] = []
    monkeypatch.setattr(tracing, "set_current_trace_io", lambda **kw: calls.append(kw))
    _pipeline(StubDetector(RiskTier.L0), SpyNotifier()).process_text("", elder_id="u1")
    assert calls == [{"user_input": "", "assistant_output": NOT_HEARD_REPLY}]


class BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("模型掛了")


class BoomTts:
    def synthesize(self, text: str) -> TtsResult:
        raise TTSError("合成失敗")


def _traced_pipeline(traces, *, tts=None, llm=None, detector=None):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(llm or EchoLLM(), NullSession()),
        tts=tts or TextBubbleTts(),
        detector=detector or StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        traces=traces,
        model_name="test-model",
        safety_model_name="safety-model",
        timer=iter([0.0, 0.1, 0.2, 0.3, 0.5, 0.6, 0.9, 1.0]).__next__,
    )


def test_pipeline_records_all_stages_on_success():
    traces = FakeTraceStore()
    _traced_pipeline(traces).process(
        b"\x00", elder_id="u1", trace_id="t1", audio_url="https://x/in.m4a"
    )
    assert len(traces.asr_calls) == 1
    assert traces.asr_calls[0].status == "ok"
    assert traces.asr_calls[0].transcript == "阿公早安"
    assert traces.asr_calls[0].source_audio_url == "https://x/in.m4a"
    assert traces.asr_calls[0].latency_ms == 100  # timer 0.0 → 0.1
    # llm_calls[0]＝危急分級（✅ 庚-10）、[1]＝回覆生成
    assert traces.llm_calls[1].status == "ok"
    assert traces.llm_calls[1].model_name == "test-model"
    assert traces.llm_calls[1].content == "你說的是：阿公早安"
    assert traces.tts_calls[0].status == "ok"


def test_pipeline_records_safety_classification_as_llm_call():
    """✅ 庚-10（A-9）：危急分級呼叫補記 llm_call trace（模型名＝安全模型）。"""
    traces = FakeTraceStore()
    _traced_pipeline(traces).process(b"\x00", elder_id="u1", trace_id="t1")
    assert len(traces.llm_calls) == 2
    safety = traces.llm_calls[0]
    assert safety.model_name == "safety-model"
    assert safety.status == "ok"
    assert "L0" in safety.content
    assert safety.trace_id == "t1"


class _UsageReportingDetector:
    """分級時申報 token（模擬真 LlmRiskClassifier 經 GeminiClient 透出 usage）。"""

    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        report_llm_usage(30, 5)
        return RiskAssessment(RiskTier.L0, 0.9, "stub", ["llm"])


def test_pipeline_collects_safety_tokens_separately_from_agent():
    """✅ 庚-10：分級 token 記在分級那筆、不混進回覆生成那筆。"""
    traces = FakeTraceStore()
    _traced_pipeline(traces, detector=_UsageReportingDetector()).process(
        b"\x00", elder_id="u1", trace_id="t1"
    )
    assert traces.llm_calls[0].input_tokens == 30
    assert traces.llm_calls[0].output_tokens == 5
    assert traces.llm_calls[1].input_tokens is None  # agent 那筆不含分級 token


def test_pipeline_records_safety_failsafe_as_error():
    """分級器故障（fail-safe，從不拋例外）→ 該筆 llm_call 記 error 供觀測。"""
    traces = FakeTraceStore()
    _traced_pipeline(traces, detector=StubFailsafeDetector()).process(
        b"\x00", elder_id="u1", trace_id="t1"
    )
    assert traces.llm_calls[0].status == "error"


def test_pipeline_records_llm_error_and_reraises():
    traces = FakeTraceStore()
    with pytest.raises(LLMError):
        _traced_pipeline(traces, llm=BoomLLM()).process(b"\x00", elder_id="u1", trace_id="t1")
    assert traces.llm_calls[1].status == "error"
    assert "模型掛了" in traces.llm_calls[1].error_message
    assert traces.tts_calls == []  # LLM 失敗即中止，不會記 TTS


def test_pipeline_records_tts_degradation_and_still_replies_text():
    traces = FakeTraceStore()
    result = _traced_pipeline(traces, tts=BoomTts()).process(b"\x00", elder_id="u1", trace_id="t1")
    assert result.audio is None
    assert traces.tts_calls[0].status == "error"


class _NonTtsErrorTts:
    def synthesize(self, text):
        raise RuntimeError("unexpected")


def test_pipeline_records_tts_non_ttserror_then_propagates():
    # 統一 _span 後，tts 的非 TTSError 失敗也會留痕（再往外拋，對話行為不變）。
    traces = FakeTraceStore()
    with pytest.raises(RuntimeError):
        _traced_pipeline(traces, tts=_NonTtsErrorTts()).process(
            b"\x00", elder_id="u1", trace_id="t1"
        )
    assert traces.tts_calls[0].status == "error"


def test_pipeline_passes_trace_id_to_risk_events():
    traces = FakeTraceStore()
    risk_events = FakeRiskEventStore()
    pipeline = VoicePipeline(
        asr=MockAsrClient("救命"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L2),
        notifier=SpyNotifier(),
        risk_events=risk_events,
        traces=traces,
    )
    pipeline.process(b"\x00", elder_id="u1", trace_id="t7")
    assert risk_events.recorded_trace_ids == ["t7"]


def test_pipeline_without_traces_keeps_working():
    notifier = SpyNotifier()
    result = _pipeline(StubDetector(RiskTier.L0), notifier).process(b"\x00", elder_id="u1")
    assert result.text == "你說的是：阿公早安"


class _ExplodingAsr:
    def transcribe(self, audio, *, content_type):
        raise AssertionError("process_text 不應呼叫 ASR")


def _text_pipeline(
    detector,
    notifier,
    risk_events=None,
    *,
    reminder_logs=None,
    moderator=None,
    combined_classifier=None,
    traces=None,
):
    return VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
        reminder_logs=reminder_logs,
        response_window_seconds=3600,
        moderator=moderator,
        combined_classifier=combined_classifier,
        traces=traces,
    )


def test_process_text_skips_asr_and_replies():
    notifier = SpyNotifier()
    result = _text_pipeline(StubDetector(RiskTier.L0), notifier).process_text(
        "我想聊天", elder_id="u1"
    )
    assert result.text == "你說的是：我想聊天"
    assert result.transcript == "我想聊天"
    assert notifier.calls == []


def test_process_text_notifies_and_records_on_l3():
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _text_pipeline(StubDetector(RiskTier.L2), notifier, events).process_text(
        "救命", elder_id="u1", trace_id="t9"
    )
    assert notifier.calls == [("u1", RiskTier.L2)]
    assert events.recorded_trace_ids == ["t9"]


class StubFailsafeDetector:
    """模擬分級器故障的保守留痕輸出（✅ D-31）。"""

    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        return RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON, ["llm:error"])


def test_failsafe_l1_records_without_notifying():
    """✅ D-31（甲-5）：fail-safe L1 要落庫留痕，但不通知家屬。"""
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _text_pipeline(StubFailsafeDetector(), notifier, events).process_text(
        "今天天氣真好", elder_id="u1", trace_id="t1"
    )
    assert notifier.calls == []
    assert len(events.recorded) == 1
    assert events.recorded[0][1].reason == FAILSAFE_EVENT_REASON


def test_plain_l1_recorded_without_notifying():
    """一般 L1（小訊號）要落庫供每日摘要取用、但不通知家屬（✅ D-10 己-5，庚-01）。

    落庫是「L1 小訊號進每日摘要」的資料來源：summaries._l1_signals_for_day 只讀
    risk_events 中「L1 且非 fail-safe 理由」的事件——修復前此類事件從未被寫入，
    功能在生產路徑恆為空（05 差距 A-39）。
    """
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _text_pipeline(StubDetector(RiskTier.L1), notifier, events).process_text(
        "最近睡不好", elder_id="u1"
    )
    assert notifier.calls == []
    assert len(events.recorded) == 1
    assert events.recorded[0][0] == "u1"
    assert events.recorded[0][1].tier == RiskTier.L1
    assert events.recorded[0][1].reason != FAILSAFE_EVENT_REASON


class _UsageReportingLLM:
    """回覆時申報 token 用量（✅ D-05 戊-2）：模擬 GeminiClient 透出 usage_metadata。"""

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        report_llm_usage(120, 40)
        return "有記帳的回覆"


def test_pipeline_records_llm_token_usage():
    traces = FakeTraceStore()
    _traced_pipeline(traces, llm=_UsageReportingLLM()).process(
        b"\x00", elder_id="u1", trace_id="t1"
    )
    assert traces.llm_calls[1].input_tokens == 120
    assert traces.llm_calls[1].output_tokens == 40


def test_pipeline_records_null_tokens_when_llm_reports_no_usage():
    # 零申報（假 LLM／舊 SDK 無 usage_metadata）記 NULL＝「未量測」，與量測到 0 區隔。
    traces = FakeTraceStore()
    _traced_pipeline(traces).process(b"\x00", elder_id="u1", trace_id="t1")
    assert traces.llm_calls[1].input_tokens is None
    assert traces.llm_calls[1].output_tokens is None


def _reminders_with_one_recent(elder_id: str) -> FakeReminderLogStore:
    """五分鐘前推過一則提醒的 store（落在預設一小時回應窗內）。"""
    recent = datetime.now(UTC) - timedelta(minutes=5)
    reminders = FakeReminderLogStore(clock=lambda: recent)
    reminders.record(elder_id, REMINDER_KIND_MEDICATION, "早上用藥：血壓藥")
    return reminders


def test_incoming_text_marks_a_recent_reminder_as_responded():
    """長輩開口＝可能在回應剛推的提醒；這是反思唯一騙不了人的行為訊號。"""
    reminders = _reminders_with_one_recent("u1")

    _text_pipeline(StubDetector(RiskTier.L0), SpyNotifier(), reminder_logs=reminders).process_text(
        "我吃過了", elder_id="u1"
    )

    assert reminders.list_for_elder("u1")[0].responded_at is not None


def test_incoming_voice_marks_a_recent_reminder_as_responded():
    """語音與文字共用 _process_transcribed，故兩條路徑都要標記（語音路徑的證明）。"""
    reminders = _reminders_with_one_recent("u1")

    _pipeline(StubDetector(RiskTier.L0), SpyNotifier(), reminder_logs=reminders).process(
        b"\x00", elder_id="u1"
    )

    assert reminders.list_for_elder("u1")[0].responded_at is not None


class _SpyReminderLogs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, int]] = []

    def mark_responded(self, elder_id: str, *, now: float, within_seconds: int) -> None:
        self.calls.append((elder_id, now, within_seconds))


def test_marking_uses_wall_clock_and_configured_window():
    """now 必須是牆鐘時間（epoch 秒）：self._timer 預設 time.monotonic 只能量延遲，
    拿去跟 reminder_logs.created_at（epoch 秒）比較會得到垃圾（窗判定永遠不成立）。
    """
    spy = _SpyReminderLogs()
    pipeline = _text_pipeline(StubDetector(RiskTier.L0), SpyNotifier(), reminder_logs=spy)

    before = time.time()
    pipeline.process_text("你好", elder_id="u1")
    after = time.time()

    elder_id, now, within_seconds = spy.calls[0]
    assert elder_id == "u1"
    assert within_seconds == 3600  # 由呼叫端設定帶入，不在管線內硬編碼
    assert before <= now <= after  # monotonic（開機以來秒數）會落在這個區間外


class _OrderedNotifier:
    """與 reminder store 共用同一個呼叫序列 list，用來釘死兩者的先後。"""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def notify(self, elder_id: str, assessment: RiskAssessment, user_text: str) -> None:
        self._calls.append("notify")


class _OrderedReminderLogs:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def mark_responded(self, elder_id: str, *, now: float, within_seconds: int) -> None:
        self._calls.append("mark_responded")


def test_critical_notification_precedes_the_reminder_signal_marking():
    """家屬通報必須發生在提醒回應標記之前——這個順序是安全屬性，不是風格偏好。

    `mark_responded` 是一個 DB UPDATE，且純粹是反思用的觀測訊號（長輩開口＝可能在回應
    剛推的提醒）。管線裡的 try/except 擋得住它的**錯誤**，擋不住它的**延遲**：全庫沒有
    任何 statement_timeout／lock_timeout，撞到鎖就是無限期阻塞。真實情境——部署時
    `ensure_schema` 以非 CONCURRENTLY 方式建 reminder_logs 的索引，對該表持 ShareLock、
    擋住所有寫入；此時長輩傳來「我喘不過氣」，標記卡在鎖上，**家屬通報跟著卡住**，直到
    索引建完為止。一個給反思用的觀測訊號，不該擋在長輩的求救前面。

    時間窗語意與本輪中的位置無關（`mark_responded` 用 time.time() 判斷提醒發出後 N 秒內
    長輩有沒有發言），所以搬到通報之後零成本。⚠️ 請不要「順手優化」把它搬回開頭。
    """
    calls: list[str] = []
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L2),
        _OrderedNotifier(calls),
        reminder_logs=_OrderedReminderLogs(calls),
    )

    pipeline.process_text("我喘不過氣", elder_id="u1")

    assert calls.index("notify") < calls.index("mark_responded")


class _OrderedModerator:
    """與 notifier 共用同一個呼叫序列 list，用來釘死審核相對於家屬通報的先後。"""

    def __init__(self, calls: list[str], result: ModerationResult) -> None:
        self._calls = calls
        self._result = result

    def moderate(self, text: str) -> ModerationResult:
        self._calls.append("moderate")
        return self._result


_BLOCK_HIJACK = ModerationResult(AbuseCategory.ROLE_HIJACK, 0.95, "要求扮演", ["llm"])
_ALLOW = ModerationResult(AbuseCategory.NONE, 0.1, "正常發話", ["llm"])


def test_moderation_runs_after_family_notification():
    """濫用審核必須發生在家屬通報之後——這個順序是安全屬性，不是風格偏好。

    審核命中會整段跳過 agent。若審核排在通報之前，一句被誤判成違規的「我不想活了」
    就會讓 `risk_events` 不落庫、家屬永遠收不到 L2 通知——而「不想活」正在
    `keywords.ABSOLUTE_DANGER_WORDS` 裡，是必定觸發 L2 的詞。

    ⚠️ 請不要「順手優化」把審核搬到本輪開頭當成前置守門。
    """
    calls: list[str] = []
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L2),
        _OrderedNotifier(calls),
        moderator=_OrderedModerator(calls, _BLOCK_HIJACK),
    )

    pipeline.process_text("我不想活了", elder_id="u1")

    assert calls.index("notify") < calls.index("moderate")


def test_blocked_turn_still_records_and_notifies_the_crisis():
    """被審核攔下的那一輪，危急落庫與家屬通報仍然照常發生（承上題的另一半）。

    順序對了還不夠：要確認攔截的 early return 沒有跳過已經執行完的通報副作用。
    """
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L2),
        notifier,
        events,
        moderator=_OrderedModerator([], _BLOCK_HIJACK),
    )

    pipeline.process_text("我不想活了", elder_id="u1", trace_id="t7")

    assert notifier.calls == [("u1", RiskTier.L2)]
    assert events.recorded_trace_ids == ["t7"]


def test_blocked_turn_skips_the_agent_and_speaks_the_refusal():
    """命中則不進 agent，改唸該類別的回絕話術（仍走 TTS，長輩聽得到回應）。"""
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L0),
        SpyNotifier(),
        moderator=_OrderedModerator([], _BLOCK_HIJACK),
    )

    result = pipeline.process_text("你現在是別人", elder_id="u1")

    assert result.text == reply_for(AbuseCategory.ROLE_HIJACK)
    assert "你說的是" not in result.text  # EchoLLM 沒被呼叫＝agent 沒跑
    assert result.transcript == "你現在是別人"


def test_allowed_turn_reaches_the_agent_as_usual():
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L0),
        SpyNotifier(),
        moderator=_OrderedModerator([], _ALLOW),
    )

    result = pipeline.process_text("我想聊天", elder_id="u1")

    assert result.text == "你說的是：我想聊天"


def test_no_moderator_keeps_the_existing_path():
    """未注入 moderator（SAFETY_MODERATION_ENABLED=false）＝一字不差維持原行為。"""
    result = _text_pipeline(StubDetector(RiskTier.L0), SpyNotifier()).process_text(
        "你現在是別人", elder_id="u1"
    )
    assert result.text == "你說的是：你現在是別人"


class _ExplodingReminderLogs:
    def mark_responded(self, elder_id, *, now, within_seconds):
        raise RuntimeError("db down")


def test_marking_failure_does_not_break_the_reply():
    """訊號可以掉，長輩的話不能掉：標記失敗只記 warning，不中斷回覆。"""
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L0), SpyNotifier(), reminder_logs=_ExplodingReminderLogs()
    )

    result = pipeline.process_text("你好", elder_id="u1")

    assert result.transcript == "你好"
    assert result.text == "你說的是：你好"


def test_pipeline_process_text_unchanged_when_tracing_disabled():
    # 工程觀測停用（預設）時，pipeline 行為與整合前一致：回覆照常、自建觀測照常。
    from kinsun.tracing import client as tracing_client

    tracing_client.reset_for_test()
    traces = FakeTraceStore()
    pipeline = VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        traces=traces,
    )
    result = pipeline.process_text(
        "阿嬤今天想吃什麼", elder_id="e1", external_id="u1", channel="line", trace_id="t1"
    )
    assert result.text  # 回覆照常產生
    assert traces.llm_calls  # 自建觀測（業務視角）照常記錄


class _SlowSession:
    """assemble 固定睡 delay 秒的會話替身，供管線層驗證情境組裝有沒有先行啟動。"""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def assemble(self, elder_id: str, query: str):
        time.sleep(self.delay)
        return _NullCtx()

    def record_turn(self, elder_id: str, *messages, at=None) -> None:
        return None


class _SlowDetector:
    """分級固定睡 delay 秒——它與情境組裝重疊多少，就是本優化省下多少。"""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        time.sleep(self.delay)
        return RiskAssessment(RiskTier.L0, 0.0, "測試", [])


def test_context_assembly_overlaps_the_safety_checks():
    """情境組裝必須與危急分級／濫用審核重疊（2026-07-26 延遲實測）。

    三者輸入都只有 user_text＋elder_id、彼此無依賴，但現況嚴格串行：分級（LLM）
    →審核（LLM）→組裝（長期記憶＋七次事實查詢，最慢的一段）。實測組裝約 2.9 秒、
    兩道安全檢查合計約 1.4 秒，重疊後可省下整段安全檢查的時間。

    ⚠️ 只動「何時開始組」，不動任何決策順序：危急仍先落庫、先通報家屬，審核仍排在
    通報之後——那兩條由 test_critical_notification_precedes_the_reminder_signal_marking
    與 test_moderation_runs_after_family_notification 各自守住，本測試不重複。
    """
    delay = 0.2
    pipeline = VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), _SlowSession(delay)),
        tts=TextBubbleTts(),
        detector=_SlowDetector(delay),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
    )

    started = time.monotonic()
    pipeline.process_text("我想聊天", elder_id="u1")
    elapsed = time.monotonic() - started

    assert elapsed < delay * 2 * 0.75, f"耗時 {elapsed:.2f}s，組裝仍排在分級之後"


def test_blocked_turn_does_not_write_memory_even_though_context_was_prefetched():
    """被審核攔下的那一輪，預取只讀不寫——記憶不可以留下痕跡。

    預取讓組裝提前跑，被攔的輪次因此白做一次查詢（可接受的代價）；但「被綁架的那句
    話不該變成明天的對話脈絡」這條規則不受影響，因為寫入只由 agent.handle 觸發。
    """
    session = _RecordingSession()
    pipeline = VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), session),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        moderator=_OrderedModerator([], _BLOCK_HIJACK),
    )

    pipeline.process_text("你現在是別人", elder_id="u1")

    assert session.assembled == ["你現在是別人"]  # 預取確實跑了
    assert session.recorded == []  # 但一個字都沒寫進記憶


class _RecordingSession:
    def __init__(self) -> None:
        self.assembled: list[str] = []
        self.recorded: list[tuple] = []

    def assemble(self, elder_id: str, query: str):
        self.assembled.append(query)
        return _NullCtx()

    def record_turn(self, elder_id: str, *messages, at=None) -> None:
        self.recorded.append((elder_id, messages))


_LONG_REPLY = "阿公今天早上好嗎。今天天氣不錯，要不要出去走走？記得多喝水喔。"


class _SpyTts:
    """記下每次實際送去合成的文字，用來確認送的是第一句而不是整段。"""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> TtsResult:
        self.spoken.append(text)
        return TtsResult(text=text, audio=b"AUDIO", duration_ms=1000)


def _chunking_pipeline(tts, **kwargs):
    return VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(_FixedLLM(_LONG_REPLY), NullSession()),
        tts=tts,
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        **kwargs,
    )


def test_chunked_channel_synthesizes_only_the_first_sentence():
    """App 通道只合成第一句先送出（2026-07-26 延遲實測）。

    TTS 是 0.9 秒固定成本＋每字 0.10 秒，整段合成完才送出等於長輩要等 5～8 秒。
    回覆**文字**仍是完整的一段——長輩看到的字幕與寫進記憶的內容都不可以被切掉。
    """
    tts = _SpyTts()
    # 2026-08-01：分段另需宣告內嵌投遞，見 turn_context.inline_audio_delivery
    with turn_context.inline_audio_delivery(True):
        result = _chunking_pipeline(tts, chunked_channels=frozenset({"app"})).process_text(
            "我想聊天", elder_id="u1", channel="app"
        )

    assert tts.spoken == ["阿公今天早上好嗎。"]  # 只合成第一句
    assert result.text == _LONG_REPLY  # 但文字是完整的
    # 兩段而非三段：末句「記得多喝水喔。」只有 7 字，低於門檻故往前併（見 chunking）。
    assert result.chunk_count == 2  # 讓 App 知道總共幾段


def test_unchunked_channel_still_synthesizes_the_whole_reply():
    """LINE（與任何未列入的通道）行為一字不變：整段合成、沒有後續段落。"""
    tts = _SpyTts()
    result = _chunking_pipeline(tts, chunked_channels=frozenset({"app"})).process_text(
        "我想聊天", elder_id="u1", channel="line"
    )

    assert tts.spoken == [_LONG_REPLY]
    assert result.chunk_count == 0


def test_chunking_defaults_to_off():
    """未指定 chunked_channels＝所有通道都維持原行為（既有呼叫端不受影響）。"""
    tts = _SpyTts()
    result = _chunking_pipeline(tts).process_text("我想聊天", elder_id="u1", channel="app")

    assert tts.spoken == [_LONG_REPLY]
    assert result.chunk_count == 0


def test_short_reply_is_not_chunked_even_on_a_chunked_channel():
    """只切得出一段的短回覆不分段——分段的代價（多一次往返）換不到任何東西。"""
    tts = _SpyTts()
    pipeline = VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(_FixedLLM("阿公您今天過得好嗎"), NullSession()),
        tts=tts,
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        chunked_channels=frozenset({"app"}),
    )

    # 2026-08-01：分段另需宣告內嵌投遞，見 turn_context.inline_audio_delivery
    with turn_context.inline_audio_delivery(True):
        result = pipeline.process_text("我想聊天", elder_id="u1", channel="app")

    assert tts.spoken == ["阿公您今天過得好嗎"]
    assert result.chunk_count == 0


def test_chunking_requires_inline_audio_delivery():
    """走 POST 降級路徑（非內嵌投遞）時不分段——否則長輩只拿得到第一句。"""
    tts = _SpyTts()
    with turn_context.inline_audio_delivery(False):
        result = _chunking_pipeline(tts, chunked_channels=frozenset({"app"})).process_text(
            "我想聊天", elder_id="u1", channel="app"
        )

    assert tts.spoken == [_LONG_REPLY], "非內嵌投遞應合成完整回覆，不是第一句"
    assert result.chunk_count == 0


class _FixedLLM:
    """固定回同一句話的 LLM 替身，讓分段測試能斷言確切的切句結果。"""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return self._reply


# --- 一輪的總時間預算（辛-21）---


class _BudgetPeekingLLM:
    """把每次被呼叫時「本輪還剩幾秒」記下來，供斷言檢查預算確實傳到了 LLM 層。"""

    def __init__(self) -> None:
        self.seen: list[float | None] = []

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        from kinsun.turn_context import remaining_budget

        self.seen.append(remaining_budget())
        return "好"


class _SlowAsr:
    """假 ASR：辨識本身要花掉一段預算（真實情況 2～7 秒，那晚是 7.0 秒）。"""

    def __init__(self, clock: list[float], seconds: float, text: str = "阿公早安") -> None:
        self._clock = clock
        self._seconds = seconds
        self._text = text

    def transcribe(self, audio: bytes, *, content_type: str = "audio/m4a") -> str:
        self._clock[0] += self._seconds
        return self._text


def test_a_turn_gets_a_budget(monkeypatch):
    """長輩開口的那一刻預算就開始跑——沒有預算，三道呼叫會各自等滿逾時。"""
    import kinsun.turn_context as tc

    monkeypatch.setattr(tc.time, "monotonic", lambda: 1000.0)
    llm = _BudgetPeekingLLM()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(llm, NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        turn_budget_seconds=30.0,
    )

    pipeline.process(b"\x00", elder_id="u1")

    assert llm.seen == [30.0]


def test_the_budget_covers_speech_recognition_too(monkeypatch):
    """ASR 花掉的時間算在預算裡：長輩等的是從按完到聽見，不是從模型開工到聽見。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])
    llm = _BudgetPeekingLLM()
    pipeline = VoicePipeline(
        asr=_SlowAsr(clock, 7.0),
        agent=CareAgent(llm, NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        turn_budget_seconds=30.0,
    )

    pipeline.process(b"\x00", elder_id="u1")

    assert llm.seen == [23.0]


def test_the_text_path_gets_a_budget_as_well(monkeypatch):
    """LINE 文字路徑同樣要有上限——它跑的是同一條管線、同一批 LLM 呼叫。"""
    import kinsun.turn_context as tc

    monkeypatch.setattr(tc.time, "monotonic", lambda: 1000.0)
    llm = _BudgetPeekingLLM()
    pipeline = VoicePipeline(
        asr=MockAsrClient("不會用到"),
        agent=CareAgent(llm, NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        turn_budget_seconds=30.0,
    )

    pipeline.process_text("阿公早安", elder_id="u1")

    assert llm.seen == [30.0]


def test_no_budget_configured_means_no_limit(monkeypatch):
    """0＝關掉這個功能（回到逐次逾時）。既有呼叫端與測試一字不必改。"""
    import kinsun.turn_context as tc

    monkeypatch.setattr(tc.time, "monotonic", lambda: 1000.0)
    llm = _BudgetPeekingLLM()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(llm, NullSession()),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        turn_budget_seconds=0.0,
    )

    pipeline.process(b"\x00", elder_id="u1")

    assert llm.seen == [None]


# ── 分級＋審核合併成一次 Gemini 呼叫（2026-07-30 延遲優化 C2） ──────────────


class _FakeCombinedClassifier:
    """測試替身：依建構時給的結果原樣回傳，記下每次被呼叫的原話。"""

    def __init__(self, result: CombinedSafetyResult) -> None:
        self._result = result
        self.calls: list[str] = []

    def classify(self, text: str, *, recent: list[str] | None = None) -> CombinedSafetyResult:
        self.calls.append(text)
        return self._result


class _BoomRiskClassifier:
    """走錯路徑的探針：合併模式下不該有人呼叫分級器本體。"""

    def classify(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        raise AssertionError("走錯路徑：合併模式應呼叫 combine_with_llm，不是分級器本體")


class _BoomAbuseClassifier:
    """走錯路徑的探針：合併模式下不該有人呼叫審核分類器本體。"""

    def classify(self, text: str) -> ModerationResult:
        raise AssertionError("走錯路徑：合併模式應呼叫 apply_threshold，不是審核分類器本體")


def test_combined_classifier_replaces_both_separate_calls():
    """兩者都設定時，只呼叫一次合併分類器；分級器與審核分類器本體完全不會被呼叫到。"""
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L0, 0.9, "一般閒聊", ["llm"]),
            moderation=ModerationResult(AbuseCategory.NONE, 0.9, "正常發話", ["llm"]),
        )
    )
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        SpyNotifier(),
        moderator=AbuseModerator(_BoomAbuseClassifier()),
        combined_classifier=combined,
    )

    result = pipeline.process_text("我想聊天", elder_id="u1")

    assert combined.calls == ["我想聊天"]
    assert result.text == "你說的是：我想聊天"


def test_combined_classifier_ignored_when_moderation_disabled():
    """單獨設定合併分類器（審核關閉）沒有意義：整段不使用，回到原本只分級的路徑。"""
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L2, 0.9, "不該用到", ["llm"]),
            moderation=ModerationResult(AbuseCategory.NONE, 0.9, "不該用到", ["llm"]),
        )
    )
    notifier = SpyNotifier()
    pipeline = _text_pipeline(
        StubDetector(RiskTier.L0),
        notifier,
        moderator=None,
        combined_classifier=combined,
    )

    pipeline.process_text("我想聊天", elder_id="u1")

    assert combined.calls == []
    assert notifier.calls == []


def test_combined_path_blocked_turn_still_notifies_the_crisis():
    """合併模式下的安全屬性與分開呼叫時等價（承上面被攔截仍照常通報那題）。

    即使合併呼叫回傳的審核判斷判定攔截，危急落庫與家屬通報仍然照常先發生——
    `moderation` 雖然已經在同一次呼叫裡拿到手，但要等這裡的落庫／通報跑完
    才會被查看是否攔截（見 `combined_classifier` 模組頂端說明）。
    """
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L2, 0.95, "求救", ["llm"]),
            moderation=ModerationResult(AbuseCategory.ROLE_HIJACK, 0.95, "誤判", ["llm"]),
        )
    )
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        notifier,
        events,
        moderator=AbuseModerator(_BoomAbuseClassifier()),
        combined_classifier=combined,
    )

    result = pipeline.process_text("我不想活了", elder_id="u1", trace_id="t7")

    assert notifier.calls == [("u1", RiskTier.L2)]
    assert events.recorded_trace_ids == ["t7"]
    assert result.text == reply_for(AbuseCategory.ROLE_HIJACK)


def test_combined_path_applies_keyword_floor_and_confidence_threshold():
    """合併模式仍套用與分開呼叫時完全相同的決策規則：關鍵詞地板、審核信心門檻。"""
    # LLM 判 L0，但關鍵詞地板（症狀詞）撐住 L2；審核判違規但信心不足 0.5＜0.7 應放行。
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L0, 0.9, "沒看出來", ["llm"]),
            moderation=ModerationResult(AbuseCategory.ROLE_HIJACK, 0.5, "拿不準", ["llm"]),
        )
    )
    notifier = SpyNotifier()
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        notifier,
        moderator=AbuseModerator(_BoomAbuseClassifier(), min_confidence=0.7),
        combined_classifier=combined,
    )

    result = pipeline.process_text("我一直痛", elder_id="u1")

    assert notifier.calls == [("u1", RiskTier.L2)]  # 關鍵詞地板撐住 L2、家屬應收到通知
    assert result.text == "你說的是：我一直痛"  # 審核信心不足放行，照常進 agent


class _BoomCombinedClassifier:
    def classify(self, text: str, *, recent: list[str] | None = None) -> CombinedSafetyResult:
        raise RuntimeError("boom")


def test_combined_classifier_failure_falls_back_to_failsafe_and_failopen():
    """合併分類器整段失敗（網路例外等）：風險面 fail-safe、審核面 fail-open，絕不中斷對話。"""
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        SpyNotifier(),
        moderator=AbuseModerator(_BoomAbuseClassifier()),
        combined_classifier=_BoomCombinedClassifier(),
    )

    result = pipeline.process_text("今天天氣真好", elder_id="u1")

    assert result.text == "你說的是：今天天氣真好"  # 審核 fail-open，照常進 agent


class _OrderProbeModeration:
    """`is_blocked` 被**讀取**的那一刻登記進共用序列，用來釘死查看時機。

    這是 `test_moderation_runs_after_family_notification` 在合併模式下的真正對應：
    合併之後審核結論在通報前就已經到手，能守的不再是「呼叫時刻」而是「查看時刻」。
    """

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.category = AbuseCategory.NONE
        self.confidence = 1.0
        self.reason = "正常發話"
        self.signals = ["llm"]

    @property
    def is_blocked(self) -> bool:
        self._calls.append("read_blocked")
        return False


class _PassThroughModerator:
    """`apply_threshold` 原樣回傳，讓探針物件能一路走到 `is_blocked` 的查看點。"""

    def __init__(self, result) -> None:
        self._result = result

    def moderate(self, text):  # pragma: no cover - 合併模式不會走到
        raise AssertionError("合併模式不應呼叫 moderate")

    def apply_threshold(self, result):
        return self._result


def test_combined_path_reads_is_blocked_only_after_family_notification():
    """合併模式的順序鐵律：審核結論**被查看**的時刻必須晚於家屬通報。

    ⚠️ 這支測試取代不了 `test_moderation_runs_after_family_notification`——那支守的是
    分開呼叫路徑（`moderate()` 的呼叫時刻），合併模式下它根本不會被呼叫到。兩條路各由
    一支測試守，缺一不可。

    ⚠️ 請不要「順手優化」把 `is_blocked` 檢查上移到 `_assess_and_moderate` 之後
    （「反正結果已經拿到了，先擋掉可以省下落庫和通報」）——那正是本測試要擋的退化。
    """
    calls: list[str] = []
    probe = _OrderProbeModeration(calls)
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L2, 0.95, "求救", ["llm"]),
            moderation=ModerationResult(AbuseCategory.NONE, 1.0, "正常發話", ["llm"]),
        )
    )
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        _OrderedNotifier(calls),
        moderator=_PassThroughModerator(probe),
        combined_classifier=combined,
    )

    pipeline.process_text("我不想活了", elder_id="u1")

    assert calls.index("notify") < calls.index("read_blocked")


class _BoomThresholdModerator:
    """`apply_threshold` 爆炸——審核側的任何失敗都不可擋住家屬通報。"""

    def moderate(self, text):  # pragma: no cover - 合併模式不會走到
        raise AssertionError("合併模式不應呼叫 moderate")

    def apply_threshold(self, result):
        raise RuntimeError("boom")


def test_moderation_side_failure_cannot_block_the_family_notification():
    """審核側計算爆炸時，危急落庫與家屬通報仍照常發生（2026-07-30 審查 M-1）。

    分開呼叫時審核整段跑在通報**之後**，所以「審核側壞掉不可能擋住通報」是免費的
    結構保證；合併之後門檻套用被搬到通報之前，那道保證得靠程式碼自己補回來。
    """
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    combined = _FakeCombinedClassifier(
        CombinedSafetyResult(
            risk=RiskAssessment(RiskTier.L2, 0.95, "求救", ["llm"]),
            moderation=ModerationResult(AbuseCategory.NONE, 0.9, "正常", ["llm"]),
        )
    )
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        notifier,
        events,
        moderator=_BoomThresholdModerator(),
        combined_classifier=combined,
    )

    result = pipeline.process_text("我不想活了", elder_id="u1", trace_id="t8")

    assert notifier.calls == [("u1", RiskTier.L2)]
    assert events.recorded_trace_ids == ["t8"]
    assert result.text == "你說的是：我不想活了"  # fail-open：照常進 agent


class _BadCategoryLLM:
    """模型把 tier 判對，但 `category` 吐列舉外的字串（實測會發生的格式失誤）。"""

    def generate(self, *, system_prompt: str, messages: list[Message], response_schema=None) -> str:
        return (
            '{"tier": 2, "tier_confidence": 0.95, "tier_reason": "跌倒", '
            '"category": "fall_risk", "moderation_confidence": 0.9, "moderation_reason": "x"}'
        )


def test_bad_category_still_notifies_the_family():
    """端到端守 2026-07-30 審查的 CRITICAL：審核欄位的格式失誤不可吃掉危急通報。

    這是本批唯一擋得住「線上漏通報」的測試。失效時的症狀極度隱蔽：長輩照樣拿到正常
    回覆（審核 fail-open），只有家屬沒收到通知——沒有任何錯誤、沒有任何日誌指向它。
    刻意走真的 `LlmCombinedSafetyClassifier`（不是替身），因為要守的正是它的解析邏輯。
    """
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    pipeline = _text_pipeline(
        RiskDetector(_BoomRiskClassifier()),
        notifier,
        events,
        moderator=AbuseModerator(_BoomAbuseClassifier()),
        combined_classifier=LlmCombinedSafetyClassifier(_BadCategoryLLM()),
    )

    # 「我剛剛在浴室滑了一下」關鍵詞層只到 L1，tier=2 是家屬收到通知的唯一依據。
    pipeline.process_text("我剛剛在浴室滑了一下", elder_id="u1", trace_id="t9")

    assert notifier.calls == [("u1", RiskTier.L2)]
    assert events.recorded_trace_ids == ["t9"]


def test_combined_path_records_two_llm_calls_sharing_latency_without_double_counting_tokens():
    """一次呼叫記兩筆 llm_call（kind 分別為分級／審核），共用同一個 latency_ms；
    token 用量只記在分級那筆——兩邊都記會讓 admin 的跨 kind 用量加總把這次呼叫的
    token 算兩遍（見 `pipeline._assess_and_moderate` 的說明）。
    """

    class _UsageReportingCombinedClassifier:
        def classify(self, text: str, *, recent: list[str] | None = None) -> CombinedSafetyResult:
            report_llm_usage(40, 8)
            return CombinedSafetyResult(
                risk=RiskAssessment(RiskTier.L0, 0.9, "一般", ["llm"]),
                moderation=ModerationResult(AbuseCategory.NONE, 0.9, "正常", ["llm"]),
            )

    traces = FakeTraceStore()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=RiskDetector(_BoomRiskClassifier()),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        moderator=AbuseModerator(_BoomAbuseClassifier()),
        combined_classifier=_UsageReportingCombinedClassifier(),
        traces=traces,
        safety_model_name="safety-model",
        timer=iter([0.0, 0.1, 0.1, 0.1, 0.2, 0.3, 0.5, 0.6, 0.9, 1.0]).__next__,
    )

    pipeline.process(b"\x00", elder_id="u1", trace_id="t1")

    safety_calls = [c for c in traces.llm_calls if c.model_name == "safety-model"]
    assert len(safety_calls) == 2
    risk_call = next(c for c in safety_calls if "風險分級" in c.content)
    moderation_call = next(c for c in safety_calls if "濫用審核" in c.content)
    assert risk_call.latency_ms == moderation_call.latency_ms
    assert risk_call.input_tokens == 40
    assert risk_call.output_tokens == 8
    assert moderation_call.input_tokens is None
    assert moderation_call.output_tokens is None


# ── 記憶寫入在交出回應前收斂（2026-07-30 延遲優化 B2＋審查 H2）─────────


class _TimedWriteSession:
    """記下 `record_turn` 何時真的寫完，用來釘死「回應交出前記憶已落地」。"""

    def __init__(self, delay: float = 0.0) -> None:
        self.written: list[float] = []
        self._delay = delay

    def assemble(self, elder_id: str, query: str) -> _NullCtx:
        return _NullCtx()

    def record_turn(self, elder_id: str, *messages: Message, at=None) -> None:
        if self._delay:
            time.sleep(self._delay)
        self.written.append(time.monotonic())


def test_memory_is_settled_before_the_reply_is_handed_back():
    """回應交出前，本輪記憶必須已經落地（審查 H2）。

    ⚠️ 這條不變式原本被 REST 續拉端點（`channels/app/turns.py::get_turn_chunk`）明文
    依賴：它讀 `turns` 表拿「今天最後一則金孫回覆」算 digest，落後時 App 續拉會收到
    409 而停止——長輩只聽到第一句，其餘無聲消失，兩端都沒有任何訊號。該端點已隨
    2026-08-01「續段語音 WS 直送」移除，這個理由不再成立；現在較弱的理由是併發輪
    （見 `pipeline.py::_settle_memory_write` docstring）：下一輪讀 `turns` 表組情境
    時，若這筆寫入還沒落地，就會少了金孫剛講過的那句話。
    `record_turn` 背景化（B2）省的是 TTS 前的 0.4–1 秒，不是放棄這條不變式。
    """
    background.configure(max_workers=1)
    try:
        session = _TimedWriteSession(delay=0.05)
        pipeline = VoicePipeline(
            asr=MockAsrClient("阿公早安"),
            agent=CareAgent(EchoLLM(), session),
            tts=TextBubbleTts(),
            detector=StubDetector(RiskTier.L0),
            notifier=SpyNotifier(),
            risk_events=FakeRiskEventStore(),
        )

        pipeline.process(b"\x00", elder_id="u1")
        handed_back = time.monotonic()

        assert session.written, "記憶根本沒寫"
        assert session.written[0] <= handed_back, "回應交出時記憶還沒落地"
    finally:
        background.reset_for_test()


def test_a_lagging_memory_write_warns_but_still_returns_the_reply(caplog):
    """等不到也照樣把回覆交出去——長輩聽到回應永遠優先；但要留下看得見的 warning。"""
    import kinsun.pipeline as pipeline_module

    background.configure(max_workers=1)
    try:
        released = threading.Event()

        class _StuckSession(_TimedWriteSession):
            def record_turn(self, elder_id: str, *messages: Message, at=None) -> None:
                released.wait(timeout=5)

        original = pipeline_module._MEMORY_WRITE_SETTLE_SECONDS
        pipeline_module._MEMORY_WRITE_SETTLE_SECONDS = 0.05
        try:
            pipeline = VoicePipeline(
                asr=MockAsrClient("阿公早安"),
                agent=CareAgent(EchoLLM(), _StuckSession()),
                tts=TextBubbleTts(),
                detector=StubDetector(RiskTier.L0),
                notifier=SpyNotifier(),
                risk_events=FakeRiskEventStore(),
            )
            with caplog.at_level("WARNING", logger="kinsun.pipeline"):
                result = pipeline.process(b"\x00", elder_id="u1")
        finally:
            pipeline_module._MEMORY_WRITE_SETTLE_SECONDS = original
            released.set()

        assert result.text == "你說的是：阿公早安"
        assert "尚未落地" in caplog.text
    finally:
        background.reset_for_test()


class _ContextSpyDetector:
    """記下分級器收到的脈絡，讓「近幾輪有沒有真的送進去」測得出來。"""

    def __init__(self) -> None:
        self.recent: list[str] | None = None

    def assess(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        self.recent = recent
        return RiskAssessment(RiskTier.L0, 0.9, "stub", ["llm"])


def test_pipeline_feeds_earlier_elder_utterances_into_risk_assessment():
    """危急分級要看得到同一段對話稍早的話（2026-08-01 正式環境實況，見 classifier）。

    只送長輩自己說的話：金孫的安撫話術帶著危急詞彙，混進去會讓分級器對著自己的
    回覆升級。
    """
    detector = _ContextSpyDetector()
    pipeline = VoicePipeline(
        asr=MockAsrClient("為什麼一定要找家人"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        recent_utterances=lambda elder_id: ["我要去西方極樂世界囉"],
    )
    pipeline.process(b"\x00", elder_id="u1")
    assert detector.recent == ["我要去西方極樂世界囉"]


def test_pipeline_without_the_dependency_passes_no_context():
    """未接線時逐字維持原行為——既有呼叫端與測試不受影響。"""
    detector = _ContextSpyDetector()
    _pipeline(detector, SpyNotifier()).process(b"\x00", elder_id="u1")
    assert detector.recent == []
