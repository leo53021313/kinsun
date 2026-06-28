from kinsun.agent import CareAgent
from kinsun.llm import Message
from kinsun.pipeline import VoicePipeline
from kinsun.safety.tiers import RiskAssessment, RiskTier
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts


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


def _pipeline(detector, notifier):
    return VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullMemory(), NullContext()),
        tts=TextBubbleTts(),
        detector=detector,
        notifier=notifier,
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
