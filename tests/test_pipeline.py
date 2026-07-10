import pytest

from kinsun.agent import CareAgent
from kinsun.llm import LLMError, Message, report_llm_usage
from kinsun.pipeline import VoicePipeline
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts, TTSError, TtsResult
from tests.fakes import FakeRiskEventStore, FakeTraceStore


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


class _NullCtx:
    system_suffix = ""
    history: list[Message] = []


class NullSession:
    def assemble(self, elder_id: str, query: str) -> _NullCtx:
        return _NullCtx()

    def record_turn(self, elder_id: str, *messages: Message) -> None:
        pass


class StubDetector:
    def __init__(self, tier: RiskTier) -> None:
        self._tier = tier

    def assess(self, text: str) -> RiskAssessment:
        return RiskAssessment(self._tier, 0.9, "stub", ["llm"])


class SpyNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RiskTier]] = []

    def notify(self, elder_id: str, assessment: RiskAssessment) -> None:
        self.calls.append((elder_id, assessment.tier))


def _pipeline(detector, notifier, risk_events=None):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
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


def test_pipeline_does_not_record_below_l2():
    events = FakeRiskEventStore()
    _pipeline(StubDetector(RiskTier.L1), SpyNotifier(), events).process(b"\x00", elder_id="u1")
    assert events.recorded == []


class _BoomAgent:
    def handle(self, elder_id, user_text):
        raise RuntimeError("llm down")


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


class BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("模型掛了")


class BoomTts:
    def synthesize(self, text: str) -> TtsResult:
        raise TTSError("合成失敗")


def _traced_pipeline(traces, *, tts=None, llm=None):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(llm or EchoLLM(), NullSession()),
        tts=tts or TextBubbleTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
        traces=traces,
        model_name="test-model",
        timer=iter([0.0, 0.1, 0.2, 0.5, 0.6, 0.9]).__next__,
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
    assert traces.llm_calls[0].status == "ok"
    assert traces.llm_calls[0].model_name == "test-model"
    assert traces.llm_calls[0].content == "你說的是：阿公早安"
    assert traces.tts_calls[0].status == "ok"


def test_pipeline_records_llm_error_and_reraises():
    traces = FakeTraceStore()
    with pytest.raises(LLMError):
        _traced_pipeline(traces, llm=BoomLLM()).process(b"\x00", elder_id="u1", trace_id="t1")
    assert traces.llm_calls[0].status == "error"
    assert "模型掛了" in traces.llm_calls[0].error_message
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


def _text_pipeline(detector, notifier, risk_events=None):
    return VoicePipeline(
        asr=_ExplodingAsr(),
        agent=CareAgent(EchoLLM(), NullSession()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
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

    def assess(self, text: str) -> RiskAssessment:
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


def test_plain_l1_not_recorded():
    """一般 L1（非 fail-safe）維持不落庫、不通知。"""
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _text_pipeline(StubDetector(RiskTier.L1), notifier, events).process_text(
        "最近睡不好", elder_id="u1"
    )
    assert notifier.calls == []
    assert events.recorded == []


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
    assert traces.llm_calls[0].input_tokens == 120
    assert traces.llm_calls[0].output_tokens == 40


def test_pipeline_records_null_tokens_when_llm_reports_no_usage():
    # 零申報（假 LLM／舊 SDK 無 usage_metadata）記 NULL＝「未量測」，與量測到 0 區隔。
    traces = FakeTraceStore()
    _traced_pipeline(traces).process(b"\x00", elder_id="u1", trace_id="t1")
    assert traces.llm_calls[0].input_tokens is None
    assert traces.llm_calls[0].output_tokens is None
