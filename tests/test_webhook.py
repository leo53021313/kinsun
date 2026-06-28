from types import SimpleNamespace

from fastapi.testclient import TestClient

from kinsun.agent import CareAgent
from kinsun.channels.line.webhook import FALLBACK_PROMPT, NON_AUDIO_PROMPT, create_app
from kinsun.llm import Message
from kinsun.pipeline import VoicePipeline
from kinsun.safety.tiers import RiskAssessment, RiskTier
from kinsun.speech.asr import ASRError, MockAsrClient
from kinsun.speech.tts import TextBubbleTts


class _NullDetector:
    def assess(self, text: str) -> RiskAssessment:
        return RiskAssessment(RiskTier.L0, 0.0, "", [])


class _NullNotifier:
    def notify(self, session_id: str, assessment: RiskAssessment) -> None:
        pass


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].text}"


class NullMemory:
    def recent(self, session_id: str) -> list[Message]:
        return []

    def append(self, session_id: str, message: Message) -> None:
        pass


class RecordingMemory(NullMemory):
    def __init__(self) -> None:
        self.sessions: list[str] = []

    def append(self, session_id: str, message: Message) -> None:
        self.sessions.append(session_id)


class FakeMessenger:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def get_audio(self, message_id: str) -> bytes:
        return b"\x00\x01"

    def reply_text(self, reply_token: str, text: str) -> None:
        self.replies.append((reply_token, text))


def _audio_event(user_id="U-1"):
    return SimpleNamespace(
        reply_token="rt-1",
        message=SimpleNamespace(type="audio", id="m-1"),
        source=SimpleNamespace(user_id=user_id),
    )


def _text_event():
    return SimpleNamespace(
        reply_token="rt-2",
        message=SimpleNamespace(type="text", id="m-2"),
        source=SimpleNamespace(user_id="U-2"),
    )


class FakeParser:
    def __init__(self, events):
        self._events = events

    def parse(self, body: str, signature: str):
        return self._events


def _make_client(parser, messenger, asr=None, memory=None):
    pipeline = VoicePipeline(
        asr=asr or MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), memory or NullMemory()),
        tts=TextBubbleTts(),
        detector=_NullDetector(),
        notifier=_NullNotifier(),
    )
    app = create_app(parser=parser, pipeline=pipeline, messenger=messenger)
    return TestClient(app)


def test_audio_message_replies_agent_output():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_audio_event()]), messenger)
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200
    assert messenger.replies == [("rt-1", "你說的是：阿公早安")]


def test_session_id_threaded_to_memory():
    messenger = FakeMessenger()
    memory = RecordingMemory()
    client = _make_client(FakeParser([_audio_event("U-42")]), messenger, memory=memory)
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert memory.sessions == ["U-42", "U-42"]


def test_missing_user_id_degrades_to_unknown():
    messenger = FakeMessenger()
    memory = RecordingMemory()
    client = _make_client(FakeParser([_audio_event(user_id=None)]), messenger, memory=memory)
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200
    assert memory.sessions == ["unknown", "unknown"]


def test_non_audio_message_replies_prompt():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_text_event()]), messenger)
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-2", NON_AUDIO_PROMPT)]


class BoomAsr:
    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        raise ASRError("boom")


def test_pipeline_error_replies_fallback():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_audio_event()]), messenger, asr=BoomAsr())
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-1", FALLBACK_PROMPT)]


def test_invalid_signature_returns_400():
    from linebot.v3 import WebhookParser

    real_parser = WebhookParser("real-secret")
    messenger = FakeMessenger()
    client = _make_client(real_parser, messenger)
    resp = client.post(
        "/line/webhook", content=b'{"events":[]}', headers={"X-Line-Signature": "wrong"}
    )
    assert resp.status_code == 400
