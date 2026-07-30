"""App 對講機通道測試：POST /api/app/turns 收音檔、回文字＋語音 URL。"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.agent import CareAgent
from kinsun.binding.gate import ConsentGate
from kinsun.channels.app.turns import create_app_turns_router
from kinsun.channels.inbound import VoiceReplyDelivery
from kinsun.llm import Message
from kinsun.locations.store import ElderLocation
from kinsun.pipeline import VoicePipeline
from kinsun.safety.detector import RiskDetector
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts, TtsResult
from kinsun.web.envelope import install_error_envelope
from tests.fakes import FakeAccountStore, FakeLocationStore, FakeRiskEventStore, FakeTraceStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=TPE)


class _EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


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
    """回帶音檔的 TTS（觸發語音回覆路徑）。"""

    def synthesize(self, text: str, *, voice=None) -> TtsResult:
        return TtsResult(text=text, audio=b"fake-m4a", duration_ms=1200)


class _FakePublisher:
    def publish(self, audio: bytes, *, content_type: str) -> str:
        return "https://cdn.example/reply.m4a"


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


def _client(svc, *, tts=None, publisher=None, traces=None, locations=None):
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(_EchoLLM(), _NullSession()),
        tts=tts or TextBubbleTts(),
        detector=RiskDetector(_NullClassifier()),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
        traces=traces,
    )
    voice = VoiceReplyDelivery(publisher, include_text=True)
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_turns_router(
            accounts=svc,
            pipeline=pipeline,
            gate=ConsentGate(svc),
            voice=voice,
            traces=traces,
            new_id=lambda: "trace-1",
            locations=locations,
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def _post_audio(client, token, body=b"\x00fake-audio", *, location=None, lat=None, lon=None):
    params = {}
    if location is not None:
        params["location"] = location
    if lat is not None:
        params["latitude"] = lat
    if lon is not None:
        params["longitude"] = lon
    return client.post(
        "/api/v1/turns",
        content=body,
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "audio/m4a"},
    )


def test_turn_replies_text_and_voice():
    svc = _service()
    _, token = _bound_elder_token(svc)
    res = _post_audio(_client(svc, tts=_VoiceTts(), publisher=_FakePublisher()), token)
    assert res.status_code == 201
    body = res.json()["data"]
    assert body["text"] == "你說的是：阿公早安"
    assert body["audio_url"] == "https://cdn.example/reply.m4a"
    assert body["duration_ms"] == 1200


def test_turn_degrades_to_text_without_audio():
    svc = _service()
    _, token = _bound_elder_token(svc)
    res = _post_audio(_client(svc), token)  # TextBubbleTts：無音檔
    assert res.status_code == 201
    body = res.json()["data"]
    assert body["text"] == "你說的是：阿公早安"
    assert body["audio_url"] == ""


def test_turn_records_trace_chain():
    svc = _service()
    _, token = _bound_elder_token(svc)
    traces = FakeTraceStore()
    res = _post_audio(_client(svc, traces=traces), token)
    assert res.status_code == 201
    assert len(traces.asr_calls) == 1
    assert len(traces.llm_calls) == 2  # 危急分級＋回覆生成（✅ 庚-10）
    assert len(traces.replies) == 1


def test_turn_requires_elder_token():
    svc = _service()
    client = _client(svc)
    assert _post_audio(client, "not-a-token").status_code == 401
    # 家屬 token 也不行（principal_type 不符）。
    _, guardian_token = svc.register_guardian_account("son@example.com", "correct-horse-8", "兒子")
    assert _post_audio(client, guardian_token).status_code == 401


def test_turn_blocked_after_binding_removed():
    """token 不代表同意：App 通道綁定消失（如後台拆綁）即擋。
    （revoke_consent 已隨 D-13「不做撤回」刪除——己-8，改以拆綁定觸發同一 403 路徑。）"""
    from kinsun.accounts.models import Channel, PrincipalType

    svc = _service()
    elder, token = _bound_elder_token(svc)
    svc._repo.remove_channel_bindings_for_principal(
        Channel.APP, PrincipalType.ELDER, elder.elder_id
    )
    res = _post_audio(_client(svc), token)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "consent_revoked"


def test_turn_rejects_non_audio_content_type():
    """✅ D-61（丙-11）：對講機只收音訊 content-type，誤傳回 415。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    res = client.post(
        "/api/v1/turns",
        content=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "unsupported_media_type"


def test_turn_rejects_oversized_audio():
    svc = _service()
    _, token = _bound_elder_token(svc)
    res = _post_audio(_client(svc), token, body=b"\x00" * (10 * 1024 * 1024 + 1))
    assert res.status_code == 413


def test_location_with_coords_is_saved():
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    res = _post_audio(
        _client(svc, locations=locations), token, location="台南市", lat=22.99, lon=120.21
    )
    assert res.status_code == 201
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "台南市", NOW.timestamp(), 22.99, 120.21
    )


def test_location_without_coords_does_not_write():
    # 半套＝沒有：App 要嘛三個都給、要嘛都不給。只有地名沒有座標的分支沒有任何
    # 呼叫端會產生，接受它只會讓下游多一條沒人走的路。
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    _post_audio(_client(svc, locations=locations), token, location="台南市")
    assert locations.get_for_elder(elder.elder_id) is None


def test_coords_without_location_does_not_write():
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    _post_audio(_client(svc, locations=locations), token, lat=22.99, lon=120.21)
    assert locations.get_for_elder(elder.elder_id) is None


def test_missing_location_does_not_write():
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    _post_audio(_client(svc, locations=locations), token)
    assert locations.get_for_elder(elder.elder_id) is None


def test_blank_location_does_not_clear_existing():
    # 長輩這次沒授權／室內收不到 → 不該把上次的位置抹掉。空字串＝「這輪沒有位置」，
    # 不是「他不在任何地方」。
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    locations.save(ElderLocation(elder.elder_id, "高雄市", 1752739200.0, 22.62, 120.31))
    _post_audio(_client(svc, locations=locations), token, location="   ", lat=22.99, lon=120.21)
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "高雄市", 1752739200.0, 22.62, 120.31
    )


def test_location_write_failure_does_not_break_the_turn():
    # 位置是加分項，不是對話的前提。比照工具失敗的既有政策：記 log、對話照走。
    class _ExplodingStore:
        def save(self, location):
            raise RuntimeError("boom")

        def get_for_elder(self, elder_id):
            return None

    svc = _service()
    _, token = _bound_elder_token(svc)
    res = _post_audio(_client(svc, locations=_ExplodingStore()), token, location="台南市")
    assert res.status_code == 201
