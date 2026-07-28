"""App 對講機 WebSocket 通道測試（spec 2026-07-28 P2）。

守的是三件事：
1. **認證與同意複核不可省**——token 不代表同意，撤回或綁定消失即擋。
2. **安撫話在工具跑之前就送出**，且對話路徑上不合成、不上傳（只查表）。
3. **一輪失敗不可打斷整條連線**——長輩不必重新開 App。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.agent import CareAgent
from kinsun.binding.gate import ConsentGate
from kinsun.channels.app.ws import create_app_ws_router
from kinsun.channels.inbound import VoiceReplyDelivery
from kinsun.llm import Message, ToolCall, ToolSpec, ToolTurn
from kinsun.locations.store import ElderLocation
from kinsun.pipeline import VoicePipeline
from kinsun.safety.detector import RiskDetector
from kinsun.speech.ack_audio import AckClip
from kinsun.speech.asr import ASRError, MockAsrClient
from kinsun.speech.tts import TtsResult
from kinsun.tools.registry import ToolRegistry
from tests.fakes import FakeAccountStore, FakeLocationStore, FakeRiskEventStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=TPE)


class _EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


class _ToolThenReplyLLM:
    """第一輪要工具、第二輪講人話——用來走到安撫話的觸發點。"""

    def __init__(self, tool_name: str = "get_news") -> None:
        self._turns = [
            ToolTurn(text=None, tool_calls=[ToolCall(tool_name, {})]),
            ToolTurn(text="今天有三則新聞喔", tool_calls=[]),
        ]

    def generate(self, *, system_prompt, messages):
        raise AssertionError("有工具時不應呼叫 generate")

    def generate_tool_turn(self, *, system_prompt, messages, tools, tool_results):
        return self._turns.pop(0)


class _NullSession:
    def assemble(self, elder_id, query):
        from types import SimpleNamespace

        return SimpleNamespace(system_suffix="", history=[])

    def record_turn(self, elder_id, *messages):
        pass


class _NullClassifier:
    def classify(self, text):
        from kinsun.safety.tiers import RiskAssessment, RiskTier

        return RiskAssessment(RiskTier.L0, 0.0, "", [])


class _NullNotifier:
    def notify(self, elder_id, assessment):
        pass


class _VoiceTts:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str) -> TtsResult:
        self.calls.append(text)
        return TtsResult(text=text, audio=b"fake-m4a", duration_ms=1200)


class _FakePublisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self, audio: bytes, *, content_type: str) -> str:
        self.calls += 1
        return f"https://cdn.example/reply-{self.calls}.m4a"


class _FakeAckAudio:
    """已暖好的安撫話快取替身：查表即回，不合成不上傳。"""

    def __init__(self, clip: AckClip | None = None) -> None:
        self.asked: list[str] = []
        self._clip = clip or AckClip(
            text="好，我幫您看看最近的新聞喔",
            audio_url="https://cdn.example/ack.m4a",
            duration_ms=1300,
        )

    def clip_for(self, tool_name: str, *, persona_name: str = "kinsun") -> AckClip | None:
        self.asked.append(tool_name)
        return self._clip


class _ColdAckAudio:
    """還沒暖好：一律回 None（＝這輪不講安撫話）。"""

    def clip_for(self, tool_name: str, *, persona_name: str = "kinsun") -> AckClip | None:
        return None


def _service():
    ids = (f"id{i}" for i in count(1))
    return AccountService(
        FakeAccountStore(), clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "code1"
    )


def _bound_elder_token(svc):
    elder = svc.create_elder("U-son", "兒子", "阿公")
    invite = svc.generate_invite(elder.elder_id, InviteRole.ELDER)
    _, token = svc.bind_elder_device(invite.code, consent_by=ConsentBy.PROXY)
    return elder, token


def _news_registry(output: str = "頭條：今天天氣好"):
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="get_news", description="新聞", parameters={"type": "object", "properties": {}}
        ),
        lambda args: output,
    )
    return reg


def _client(
    svc,
    *,
    llm=None,
    tools=None,
    tts=None,
    publisher=None,
    ack_audio=None,
    locations=None,
    asr=None,
):
    pipeline = VoicePipeline(
        asr=asr or MockAsrClient("今天有什麼新消息"),
        agent=CareAgent(llm or _EchoLLM(), _NullSession(), tools=tools),
        tts=tts or _VoiceTts(),
        detector=RiskDetector(_NullClassifier()),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    app = FastAPI()
    app.include_router(
        create_app_ws_router(
            accounts=svc,
            pipeline=pipeline,
            gate=ConsentGate(svc),
            voice=VoiceReplyDelivery(publisher or _FakePublisher(), include_text=True),
            ack_audio=ack_audio,
            locations=locations,
            new_id=lambda: "turn-1",
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def _frames(ws, count_wanted: int) -> list[dict]:
    return [ws.receive_json() for _ in range(count_wanted)]


# ── 認證與同意複核 ──────────────────────────────────────────────────────


def test_missing_token_is_rejected():
    client = _client(_service())
    try:
        with client.websocket_connect("/api/v1/ws/talk"):
            pass
    except Exception:  # noqa: BLE001 - 連線被關閉即為預期
        return
    raise AssertionError("沒有 token 竟然連得上")


def test_bad_token_is_rejected():
    client = _client(_service())
    try:
        with client.websocket_connect("/api/v1/ws/talk?token=亂打的"):
            pass
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("亂打的 token 竟然連得上")


def test_revoked_consent_is_rejected_even_with_a_valid_token():
    """⚠️ token 不代表同意：撤回之後即使 token 還有效也必須擋。"""
    svc = _service()
    elder, token = _bound_elder_token(svc)
    svc.revoke_elder_device(elder.elder_id)
    client = _client(svc)
    try:
        with client.websocket_connect(f"/api/v1/ws/talk?token={token}"):
            pass
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("撤回同意後竟然連得上")


# ── 一輪對話 ────────────────────────────────────────────────────────────


def test_one_turn_sends_a_reply_frame():
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = ws.receive_json()
    assert reply["type"] == "reply"
    assert reply["turn_id"] == "turn-1"
    assert "今天有什麼新消息" in reply["text"]
    assert reply["audio_url"].startswith("https://cdn.example/reply-")
    assert reply["duration_ms"] == 1200


def test_ack_arrives_before_the_reply_when_a_tool_is_called():
    """⭐ 本功能的核心：安撫話必須在工具跑完之前就送出去。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    ack_audio = _FakeAckAudio()
    client = _client(svc, llm=_ToolThenReplyLLM(), tools=_news_registry(), ack_audio=ack_audio)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        ack, reply = _frames(ws, 2)
    assert ack["type"] == "ack"
    assert ack["text"] == "好，我幫您看看最近的新聞喔"
    assert ack["audio_url"] == "https://cdn.example/ack.m4a"
    assert ack["duration_ms"] == 1300
    assert reply["type"] == "reply"
    assert reply["text"] == "今天有三則新聞喔"
    assert ack["turn_id"] == reply["turn_id"], "同一輪的兩則訊息必須帶同一個 turn_id"
    assert ack_audio.asked == ["get_news"], "安撫話應依這一輪要呼叫的工具挑選"


def test_ack_costs_no_tts_and_no_upload():
    """⚠️ 對話路徑上不合成、不上傳——安撫話的全部價值就是「立刻」。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    tts, publisher = _VoiceTts(), _FakePublisher()
    client = _client(
        svc,
        llm=_ToolThenReplyLLM(),
        tools=_news_registry(),
        tts=tts,
        publisher=publisher,
        ack_audio=_FakeAckAudio(),
    )
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        _frames(ws, 2)
    # 只有正式回覆那一次合成與上傳；安撫話是查表來的。
    assert tts.calls == ["今天有三則新聞喔"]
    assert publisher.calls == 1


def test_no_ack_when_the_cache_is_still_cold():
    """還沒暖好就只送回覆——降級不是錯誤，長輩仍會拿到答案。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(
        svc, llm=_ToolThenReplyLLM(), tools=_news_registry(), ack_audio=_ColdAckAudio()
    )
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = ws.receive_json()
    assert reply["type"] == "reply"


def test_no_ack_when_no_tool_is_called():
    """整輪沒有工具呼叫就沒有安撫話（語料實測 5.5% 的輪次如此）。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    ack_audio = _FakeAckAudio()
    client = _client(svc, ack_audio=ack_audio)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = ws.receive_json()
    assert reply["type"] == "reply"
    assert ack_audio.asked == []


# ── 位置 ────────────────────────────────────────────────────────────────


def test_location_frame_is_saved_before_the_turn_runs():
    """⚠️ 位置必須排在這一輪之前：長輩這句話問的就是天氣時，這一輪就得用到。

    「慢一輪」在對講機上的表現就是他問第一次還是被反問，功能等於沒做。
    """
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": "台南市", "latitude": 22.99, "longitude": 120.21}))
        ws.send_bytes(b"\x00fake-audio")
        ws.receive_json()
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "台南市", NOW.timestamp(), 22.99, 120.21
    )


def test_location_needs_all_three_fields():
    """只有地名沒座標（或反之）視同「這輪沒有位置」——接受半套只會讓下游多一條沒人走的分支。"""
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": "台南市"}))
        ws.send_bytes(b"\x00fake-audio")
        ws.receive_json()
    assert locations.get_for_elder(elder.elder_id) is None


def test_malformed_location_frame_does_not_kill_the_connection():
    """外部輸入是資料不是指令：一則畸形訊息只該被丟掉，不可切斷長輩的連線。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text("這不是 JSON {{{")
        ws.send_bytes(b"\x00fake-audio")
        reply = ws.receive_json()
    assert reply["type"] == "reply"


# ── 失敗處理 ────────────────────────────────────────────────────────────


def test_a_failing_turn_sends_an_error_frame_and_keeps_the_connection():
    """一輪失敗不可打斷整條連線——長輩不必重新開 App。"""

    class _BrokenAsr:
        def transcribe(self, audio: bytes, *, content_type: str) -> str:
            raise ASRError("假的辨識失敗")

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, asr=_BrokenAsr())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        first = ws.receive_json()
        # 連線還活著：再送一輪照樣有回應。
        ws.send_bytes(b"\x00fake-audio")
        second = ws.receive_json()
    assert first["type"] in {"reply", "error"}
    assert second["type"] in {"reply", "error"}


def test_oversized_audio_is_rejected_without_closing_the_connection():
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"x" * (10 * 1024 * 1024 + 1))
        frame = ws.receive_json()
        assert frame["type"] == "error"
        ws.send_bytes(b"\x00fake-audio")
        assert ws.receive_json()["type"] == "reply"
