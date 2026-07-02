import pytest

from kinsun.agent import CareAgent
from kinsun.llm import Message
from kinsun.pipeline import VoicePipeline
from kinsun.safety.tiers import RiskAssessment, RiskTier
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts, TTSError, TtsResult
from tests.fakes import FakeRiskEventStore


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].text}"


class NullMemory:
    def recent(self, session_id: str) -> list[Message]:
        return []

    def append(self, session_id: str, message: Message) -> None:
        pass


class NullContext:
    def recall(self, session_id: str, user_text: str) -> str:
        return ""


class StubDetector:
    def __init__(self, tier: RiskTier) -> None:
        self._tier = tier

    def assess(self, text: str) -> RiskAssessment:
        return RiskAssessment(self._tier, 0.9, "stub", ["llm"])


class SpyNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RiskTier]] = []

    def notify(self, session_id: str, assessment: RiskAssessment) -> None:
        self.calls.append((session_id, assessment.tier))


def _pipeline(detector, notifier, risk_events=None):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullMemory(), NullContext()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
        risk_events=risk_events or FakeRiskEventStore(),
    )


def test_pipeline_replies_and_runs_detection():
    notifier = SpyNotifier()
    result = _pipeline(StubDetector(RiskTier.L0), notifier).process(b"\x00", session_id="u1")
    assert result.text == "你說的是：阿公早安"
    assert notifier.calls == []


def test_pipeline_notifies_on_l2_or_above():
    notifier = SpyNotifier()
    _pipeline(StubDetector(RiskTier.L3), notifier).process(b"\x00", session_id="u1")
    assert notifier.calls == [("u1", RiskTier.L3)]


class _BoomRiskEvents:
    def record(self, session_id, assessment):
        raise RuntimeError("db down")

    def list_for_session(self, session_id):
        return []


def test_pipeline_records_risk_event_on_l2():
    notifier = SpyNotifier()
    events = FakeRiskEventStore()
    _pipeline(StubDetector(RiskTier.L2), notifier, events).process(b"\x00", session_id="u1")
    assert [s for s, _ in events.recorded] == ["u1"]
    assert notifier.calls == [("u1", RiskTier.L2)]


def test_pipeline_does_not_record_below_l2():
    events = FakeRiskEventStore()
    _pipeline(StubDetector(RiskTier.L1), SpyNotifier(), events).process(b"\x00", session_id="u1")
    assert events.recorded == []


class _BoomAgent:
    def handle(self, session_id, user_text):
        raise RuntimeError("llm down")


def test_pipeline_notifies_before_reply_generation():
    """危急通知不可依賴回覆生成：agent 生成回覆丟例外時，家屬通知仍須先送出。"""
    notifier = SpyNotifier()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=_BoomAgent(),
        tts=TextBubbleTts(),
        detector=StubDetector(RiskTier.L3),
        notifier=notifier,
        risk_events=FakeRiskEventStore(),
    )
    with pytest.raises(RuntimeError):
        pipeline.process(b"\x00", session_id="u1")
    assert notifier.calls == [("u1", RiskTier.L3)]


def test_pipeline_record_failure_does_not_break():
    notifier = SpyNotifier()
    result = _pipeline(StubDetector(RiskTier.L3), notifier, _BoomRiskEvents()).process(
        b"\x00", session_id="u1"
    )
    assert result.text == "你說的是：阿公早安"
    assert notifier.calls == [("u1", RiskTier.L3)]


class _BoomTts:
    def synthesize(self, text):
        raise TTSError("tts down")


def test_pipeline_tts_failure_degrades_to_text():
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullMemory(), NullContext()),
        tts=_BoomTts(),
        detector=StubDetector(RiskTier.L0),
        notifier=SpyNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    result = pipeline.process(b"\x00", session_id="u1")
    assert isinstance(result, TtsResult)
    assert result.text == "你說的是：阿公早安"
    assert result.audio is None


def test_pipeline_sets_transcript_from_asr():
    result = _pipeline(StubDetector(RiskTier.L0), SpyNotifier()).process(b"\x00", session_id="u1")
    assert result.transcript == "阿公早安"
