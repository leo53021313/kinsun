from types import SimpleNamespace

from fastapi.testclient import TestClient

from kinsun.agent import CareAgent
from kinsun.channels.line.webhook import (
    BIND_FIRST_PROMPT,
    FALLBACK_PROMPT,
    NON_AUDIO_PROMPT,
    create_app,
)
from kinsun.llm import Message
from kinsun.pipeline import VoicePipeline
from kinsun.safety.tiers import RiskAssessment, RiskTier
from kinsun.speech.asr import ASRError, MockAsrClient
from kinsun.speech.tts import TextBubbleTts
from tests.fakes import FakeRiskEventStore


class _NullDetector:
    def assess(self, text: str) -> RiskAssessment:
        return RiskAssessment(RiskTier.L0, 0.0, "", [])


class _NullNotifier:
    def notify(self, line_user_id: str, assessment: RiskAssessment) -> None:
        pass


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


class NullMemory:
    def recent(self, line_user_id: str) -> list[Message]:
        return []

    def append(self, line_user_id: str, message: Message) -> None:
        pass


class NullContext:
    def recall(self, line_user_id: str, user_text: str) -> str:
        return ""


class RecordingMemory(NullMemory):
    def __init__(self) -> None:
        self.sessions: list[str] = []

    def append(self, line_user_id: str, message: Message) -> None:
        self.sessions.append(line_user_id)


class FakeMessenger:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def get_audio(self, message_id: str) -> bytes:
        return b"\x00\x01"

    def reply_text(self, reply_token: str, text: str) -> None:
        self.replies.append((reply_token, text))


def _audio_event(line_user_id="U-1"):
    return SimpleNamespace(
        reply_token="rt-1",
        message=SimpleNamespace(type="audio", id="m-1"),
        source=SimpleNamespace(user_id=line_user_id),
    )


def _text_event(text="設定", line_user_id="U-2"):
    return SimpleNamespace(
        reply_token="rt-2",
        message=SimpleNamespace(type="text", id="m-2", text=text),
        source=SimpleNamespace(user_id=line_user_id),
    )


def _sticker_event():
    return SimpleNamespace(
        reply_token="rt-3",
        message=SimpleNamespace(type="sticker", id="m-3"),
        source=SimpleNamespace(user_id="U-3"),
    )


class FakeParser:
    def __init__(self, events):
        self._events = events

    def parse(self, body: str, signature: str):
        return self._events


class _NullBinding:
    def handle(self, line_user_id: str, text: str):
        return None


class _StubBinding:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def handle(self, line_user_id: str, text: str):
        self.calls.append((line_user_id, text))
        return self.reply


class _AllowGate:
    def allows(self, line_user_id):
        return True


class _DenyGate:
    def allows(self, line_user_id):
        return False


def _make_client(
    parser, messenger, asr=None, memory=None, binding=None, gate=None, raise_server_exceptions=True
):
    pipeline = VoicePipeline(
        asr=asr or MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), memory or NullMemory(), NullContext()),
        tts=TextBubbleTts(),
        detector=_NullDetector(),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    app = create_app(
        parser=parser,
        pipeline=pipeline,
        messenger=messenger,
        binding=binding or _NullBinding(),
        gate=gate or _AllowGate(),
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


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
    client = _make_client(FakeParser([_audio_event(line_user_id=None)]), messenger, memory=memory)
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200
    assert memory.sessions == ["unknown", "unknown"]


def test_sticker_message_replies_prompt():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_sticker_event()]), messenger)
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-3", NON_AUDIO_PROMPT)]


def test_text_message_routes_to_binding():
    messenger = FakeMessenger()
    binding = _StubBinding("已建立檔案")
    client = _make_client(FakeParser([_text_event("設定", "U-9")]), messenger, binding=binding)
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert binding.calls == [("U-9", "設定")]
    assert messenger.replies == [("rt-2", "已建立檔案")]


def test_text_non_binding_falls_back_to_prompt():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_text_event("閒聊")]), messenger, binding=_StubBinding(None))
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-2", NON_AUDIO_PROMPT)]


def test_unconsented_voice_is_blocked():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_audio_event("U-x")]), messenger, gate=_DenyGate())
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-1", BIND_FIRST_PROMPT)]


def test_consented_voice_runs_pipeline():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_audio_event()]), messenger, gate=_AllowGate())
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-1", "你說的是：阿公早安")]


class BoomAsr:
    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        raise ASRError("boom")


def test_pipeline_error_replies_fallback():
    messenger = FakeMessenger()
    client = _make_client(FakeParser([_audio_event()]), messenger, asr=BoomAsr())
    client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.replies == [("rt-1", FALLBACK_PROMPT)]


class _BoomReplyMessenger(FakeMessenger):
    def reply_text(self, reply_token: str, text: str) -> None:
        raise RuntimeError("LINE API 失敗（例如 reply token 逾時）")


def test_reply_failure_does_not_return_500():
    # 回覆失敗（reply token 逾時、LINE API 例外等）若讓 webhook 回 500，
    # LINE 會重送整包事件 → 重複跑管線、重複發家屬危急通知。必須吞掉並回 200。
    messenger = _BoomReplyMessenger()
    client = _make_client(FakeParser([_audio_event()]), messenger, raise_server_exceptions=False)
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200


def test_one_failing_event_does_not_block_the_next():
    # 第一個事件回覆爆掉，第二個事件仍要被處理（不可整批中止）。
    class _BoomThenOk(FakeMessenger):
        def reply_text(self, reply_token: str, text: str) -> None:
            if reply_token == "rt-1":
                raise RuntimeError("第一個爆掉")
            super().reply_text(reply_token, text)

    messenger = _BoomThenOk()
    events = [_audio_event(), _sticker_event()]
    client = _make_client(FakeParser(events), messenger, raise_server_exceptions=False)
    resp = client.post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert resp.status_code == 200
    assert ("rt-3", NON_AUDIO_PROMPT) in messenger.replies


def test_invalid_signature_returns_400():
    from linebot.v3 import WebhookParser

    real_parser = WebhookParser("real-secret")
    messenger = FakeMessenger()
    client = _make_client(real_parser, messenger)
    resp = client.post(
        "/line/webhook", content=b'{"events":[]}', headers={"X-Line-Signature": "wrong"}
    )
    assert resp.status_code == 400


class _VoiceMessenger(FakeMessenger):
    def __init__(self):
        super().__init__()
        self.voice = []

    def reply_voice(self, reply_token, audio_url, duration_ms, text):
        self.voice.append((reply_token, audio_url, duration_ms, text))


class _StubTts:
    def synthesize(self, text):
        from kinsun.speech.tts import TtsResult

        return TtsResult(text=text, audio=b"AUDIO", duration_ms=700)


class _StubPublisher:
    def publish(self, audio, *, content_type):
        return "http://cdn/a.m4a"


def test_voice_reply_end_to_end():
    from kinsun.channels.inbound import VoiceReplyDelivery

    messenger = _VoiceMessenger()
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM(), NullMemory(), NullContext()),
        tts=_StubTts(),
        detector=_NullDetector(),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    app = create_app(
        parser=FakeParser([_audio_event()]),
        pipeline=pipeline,
        messenger=messenger,
        binding=_NullBinding(),
        gate=_AllowGate(),
        voice=VoiceReplyDelivery(_StubPublisher(), include_text=True),
    )
    TestClient(app).post("/line/webhook", content=b"{}", headers={"X-Line-Signature": "x"})
    assert messenger.voice == [("rt-1", "http://cdn/a.m4a", 700, "你說的是：阿公早安")]
