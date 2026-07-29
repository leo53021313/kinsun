"""App 對講機通道測試：POST /api/app/turns 收音檔、回文字＋語音 URL。"""

import asyncio
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
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

    def record_turn(self, elder_id, *messages, at=None):
        pass


class _NullClassifier:
    def classify(self, text):
        from kinsun.safety.tiers import RiskAssessment, RiskTier

        return RiskAssessment(RiskTier.L0, 0.0, "", [])


class _NullNotifier:
    def notify(self, elder_id, assessment, user_text):
        pass


class _VoiceTts:
    """回帶音檔的 TTS（觸發語音回覆路徑）。"""

    def synthesize(self, text: str) -> TtsResult:
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


# ── TTS 分段串流（2026-07-26 延遲優化）──────────────────────────────
_CHUNKED_REPLY = "阿公今天早上好嗎。今天天氣不錯，要不要出去走走？"


class _ChunkedLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return _CHUNKED_REPLY


class _SpyChunkTts:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> TtsResult:
        self.spoken.append(text)
        return TtsResult(text=text, audio=b"fake-m4a", duration_ms=900)


class _RecordingMemory:
    """短期記憶替身：分段端點靠它取回「這位長輩最後一則金孫回覆」。"""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def assemble(self, elder_id, query):
        from types import SimpleNamespace

        return SimpleNamespace(system_suffix="", history=[])

    def record_turn(self, elder_id, *messages, at=None):
        self.messages.extend(messages)

    def recent(self, elder_id):
        return list(self.messages)


class _SpyPublisher:
    def __init__(self) -> None:
        self.count = 0

    def publish(self, audio: bytes, *, content_type: str) -> str:
        self.count += 1
        return f"https://cdn.test/chunk-{self.count}.m4a"


def _chunking_client(svc, memory, tts, publisher):
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(_ChunkedLLM(), memory),
        tts=tts,
        detector=RiskDetector(_NullClassifier()),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
        chunked_channels=frozenset({"app"}),
    )
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_turns_router(
            accounts=svc,
            pipeline=pipeline,
            gate=ConsentGate(svc),
            voice=VoiceReplyDelivery(publisher, include_text=True),
            new_id=lambda: "trace-1",
            clock=lambda: NOW,
            memory=memory,
            tts=tts,
            audio_publisher=publisher,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def _chunk_setup():
    svc = _service()
    _, token = _bound_elder_token(svc)
    memory, tts, publisher = _RecordingMemory(), _SpyChunkTts(), _SpyPublisher()
    return _chunking_client(svc, memory, tts, publisher), token, tts, publisher


def test_turn_reports_chunk_count_and_digest_when_chunked():
    """App 拿到的第一段只是開頭，回應要告訴它總共幾段、以及這是哪一輪的回覆。"""
    client, token, tts, _ = _chunk_setup()

    body = _post_audio(client, token).json()["data"]

    assert body["text"] == _CHUNKED_REPLY  # 文字仍是完整的一段
    assert tts.spoken == ["阿公今天早上好嗎。"]  # 但只合成了第一句
    assert body["chunk_count"] == 2
    assert len(body["reply_digest"]) == 16


def test_fetching_the_second_chunk_synthesizes_only_that_sentence():
    client, token, tts, publisher = _chunk_setup()
    body = _post_audio(client, token).json()["data"]

    res = client.get(
        f"/api/v1/turns/chunks/1?digest={body['reply_digest']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 200
    assert res.json()["data"]["text"] == "今天天氣不錯，要不要出去走走？"
    assert res.json()["data"]["audio_url"] == "https://cdn.test/chunk-2.m4a"
    assert tts.spoken == ["阿公今天早上好嗎。", "今天天氣不錯，要不要出去走走？"]


def test_stale_digest_is_rejected_so_the_app_stops_playing_the_old_turn():
    """長輩又講了一句時，舊那輪的後續段落不可以再被播出去。"""
    client, token, _, _ = _chunk_setup()
    _post_audio(client, token)

    res = client.get(
        "/api/v1/turns/chunks/1?digest=0000000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "chunk_superseded"


def test_index_out_of_range_is_not_found():
    client, token, _, _ = _chunk_setup()
    body = _post_audio(client, token).json()["data"]

    for index in (0, 2, 99):  # 第 0 段已隨 POST 回過，2 之後不存在
        res = client.get(
            f"/api/v1/turns/chunks/{index}?digest={body['reply_digest']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404, index


def test_chunk_endpoint_requires_an_elder_token():
    client, _, _, _ = _chunk_setup()
    assert client.get("/api/v1/turns/chunks/1").status_code == 401


class _LoopWatchingAsr:
    """記下自己是不是跑在事件迴圈的執行緒上。

    `asyncio.get_running_loop()` 只有在「事件迴圈所在的執行緒」上才回傳得到迴圈；
    在工作執行緒呼叫會丟 RuntimeError。這是「這段阻塞工作有沒有佔住事件迴圈」最
    直接的判準——不依賴計時，不會偶爾紅一次。
    """

    def __init__(self) -> None:
        self.on_event_loop: bool | None = None

    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.on_event_loop = False
        else:
            self.on_event_loop = True
        return "阿公早安"


def test_the_blocking_work_never_runs_on_the_event_loop():
    """一輪對話的同步工作必須交給執行緒池，不可佔住事件迴圈。

    這支端點是 async handler，但底下整段（進站上傳、ASR、Gemini、TTS、落庫）都是
    同步阻塞呼叫。留在事件迴圈裡跑，整台後端一次就只服務得了一位長輩——2026-07-26
    全流程模擬實測：一輪對話進行中，連 GET /healthz 都要等 2.89 秒，第二位長輩開口
    得排隊，家屬 App 與觀測後台也一起卡住。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _LoopWatchingAsr()
    pipeline = VoicePipeline(
        asr=asr,
        agent=CareAgent(_EchoLLM(), _NullSession()),
        tts=TextBubbleTts(),
        detector=RiskDetector(_NullClassifier()),
        notifier=_NullNotifier(),
        risk_events=FakeRiskEventStore(),
    )
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_app_turns_router(
            accounts=svc,
            pipeline=pipeline,
            gate=ConsentGate(svc),
            voice=VoiceReplyDelivery(None, include_text=True),
            new_id=lambda: "trace-1",
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )

    assert _post_audio(TestClient(app), token).status_code == 201
    assert asr.on_event_loop is False, "對話管線跑在事件迴圈上，會把整台後端佔住"


@pytest.mark.parametrize(
    ("lat", "lon", "why"),
    [
        (999, 120.21, "緯度 999"),
        (22.99, -999, "經度 -999"),
        (90.1, 120.21, "緯度剛好越界"),
    ],
)
def test_out_of_range_coordinates_are_ignored_without_failing_the_turn(lat, lon, why):
    """座標超出範圍就當這輪沒有位置——**不可回 422**（V-04，2026-07-29）。

    422 會連長輩那句話一起退掉。位置是加分項（`_save_location` 的既有註解：
    「寫入失敗不可中斷對話」），為了一個 App 送錯的參數而讓長輩重講一次，
    代價遠大於少一筆位置。故驗證放在 `_save_location`、不放 FastAPI 簽章。
    """
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    res = _post_audio(_client(svc, locations=locations), token, location="台南市", lat=lat, lon=lon)
    assert res.status_code == 201, why
    assert locations.get_for_elder(elder.elder_id) is None, why


def test_boundary_coordinates_are_accepted_over_rest():
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    res = _post_audio(
        _client(svc, locations=locations), token, location="北極點", lat=90.0, lon=180.0
    )
    assert res.status_code == 201
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "北極點", NOW.timestamp(), 90.0, 180.0
    )
