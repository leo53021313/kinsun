"""App 對講機通道測試：POST /api/app/turns 收音檔、回文字＋語音 URL。"""

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService
from kinsun.agent import CareAgent
from kinsun.binding.gate import ConsentGate
from kinsun.channels.app.admission import TurnAdmission
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
    def classify(self, text, *, recent=None):
        from kinsun.safety.tiers import RiskAssessment, RiskTier

        return RiskAssessment(RiskTier.L0, 0.0, "", [])


class _NullNotifier:
    def notify(self, elder_id, assessment, user_text):
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
    assert body["transcript"] == "阿公早安"
    assert body["audio_url"] == "https://cdn.example/reply.m4a"
    assert body["duration_ms"] == 1200


def test_turn_degrades_to_text_without_audio():
    svc = _service()
    _, token = _bound_elder_token(svc)
    res = _post_audio(_client(svc), token)  # TextBubbleTts：無音檔
    assert res.status_code == 201
    body = res.json()["data"]
    assert body["text"] == "你說的是：阿公早安"
    assert body["transcript"] == "阿公早安"
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


# ── 容量閘門（spec 2026-07-30 §10 B2，P3 Task 2）──────────────────────────
#
# ⚠️ brief 本身沒有給這條路徑的測試案例（只給了 ws.py 的容量閘門四條＋接線步驟），
# POST 路徑同樣接了同一個 `TurnAdmission`（與 ws.py 共用）＋節流保險絲，沒有測試
# 就是接線但沒人守——尤其這條路徑的等待若不小心放錯位置，會直接卡住整個事件迴圈。


class _BlockingAsr:
    """卡在辨識裡不出來的 ASR：用來讓第一個請求一直佔著名額（與 ws.py 測試同款）。"""

    def __init__(self, transcript: str = "阿公早安") -> None:
        self._transcript = transcript
        self.entered = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        self.entered.set()
        self.release.wait(5.0)
        return self._transcript


def _admission_client(svc, *, asr, admission=None, rate_limiter=None):
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
            admission=admission,
            rate_limiter=rate_limiter,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def test_容量閘門滿載且排隊逾時時回_503_而不是裸_429_或靜默掛住():
    """長輩看不懂 429，也等不到一個永遠不會來的回應；503＋同一句人話，與 WS
    路徑同一套文案（見 `channels/app/ws.py::_BUSY_REPLY`）。

    ⚠️ 用 `with _admission_client(...) as client:`：讓兩個請求共用**同一個**
    事件迴圈（見 `test_排隊等待不佔住事件迴圈` 的說明），與正式環境「一個 worker
    一個事件迴圈」的實際情形一致，而不是各自開一個互不相干的迴圈。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _BlockingAsr()
    with _admission_client(svc, asr=asr, admission=TurnAdmission(1, queue_timeout=0.2)) as client:
        holder: dict = {}

        def send_first() -> None:
            holder["response"] = _post_audio(client, token)

        t = threading.Thread(target=send_first)
        t.start()
        assert asr.entered.wait(5.0), "第一個請求應該已經進到辨識裡、正持有名額"

        res = _post_audio(client, token, body=b"\x00second-audio")
        assert res.status_code == 503
        body = res.json()
        assert body["error"]["code"] == "too_many_requests"
        # 是人話不是狀態碼，且與 WS 路徑同一句「還在忙」——不是管線一般性失敗的文案。
        assert "還在忙" in body["error"]["message"]
        assert body["error"]["message"].startswith("我")
        assert "金孫" not in body["error"]["message"]

        asr.release.set()
        t.join(5.0)
        assert not t.is_alive()
        assert holder["response"].status_code == 201


def test_名額在請求失敗時也要釋放():
    """⚠️ 管線炸掉時若沒釋放名額，那個名額就永久消失；漏到滿之後所有人從此排隊，
    而伺服器看起來完全健康。刻意讓第一個請求**持有名額時**炸掉、且第二個請求
    **真的已經排上隊**（用 `admission.waiting()` 確認，POST 路徑沒有 WS 的
    `queued` 訊框可以回報）——兩者之間毫無時間重疊的話，即使閘門忘了寫 `with`
    （完全沒接上）這條測試也會照樣通過。

    ⚠️ 拋 `RuntimeError` 而非 `ASRError`：`channels/inbound.py::_run_pipeline`
    會把 `ASRError`／`LLMError`／`MemoryStoreError` 三種就地接住並退回覆話術，
    例外根本不會冒出 `dispatch()`，測不到閘門在未預期例外時是否正確釋放。
    """

    class _ExplodingAsr:
        """第一次呼叫卡住直到被釋放、釋放後拋出（模擬持有名額時真的炸掉）；
        第二次呼叫正常返回——與 ws.py 版本不同，這裡刻意讓第二個請求能夠
        真正完成，才能斷言它拿到 201 而非又是一次例外。"""

        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()
            self.calls = 0

        def transcribe(self, audio: bytes, *, content_type: str) -> str:
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                self.release.wait(5.0)
                raise RuntimeError("這一輪炸了（非 ASRError，管線不會就地接住）")
            return "阿公早安"

    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _ExplodingAsr()
    admission = TurnAdmission(1, queue_timeout=5.0)
    with _admission_client(svc, asr=asr, admission=admission) as client:

        def send_first() -> None:
            # 未預期例外冒到框架層是既有行為（`turns.py::_run_turn` 本來就沒有
            # try/except），本測試不關心這條路徑的 HTTP 回應，只關心名額有沒有釋放。
            try:
                _post_audio(client, token)
            except Exception:  # noqa: BLE001 - 背景執行緒吞例外只為了不留殘局
                pass

        t1 = threading.Thread(target=send_first)
        t1.start()
        assert asr.entered.wait(5.0), "第一個請求應該已經進到辨識裡、正持有名額"

        second_holder: dict = {}

        def send_second() -> None:
            second_holder["response"] = _post_audio(client, token, body=b"\x00second-audio")

        t2 = threading.Thread(target=send_second)
        t2.start()
        deadline = time.monotonic() + 2.0
        while admission.waiting() == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert admission.waiting() == 1, "第二個請求應該已經排上隊，才測得到釋放"

        asr.release.set()
        t1.join(5.0)
        t2.join(5.0)
        assert not t1.is_alive()
        assert not t2.is_alive()

        assert second_holder["response"].status_code == 201, "名額釋放後第二個請求應該正常完成"
        assert admission.active() == 0


def test_排隊等待不佔住事件迴圈_其他請求仍可進行():
    """⚠️ 這個 handler 是 async 的；若閘門的等待被誤放在事件迴圈上，會讓所有人
    的請求一起停住——包含根本沒有要用對講機的那些。用一支完全不吃閘門的探針
    端點驗證：有人真的卡在閘門的阻塞等待時，事件迴圈仍然接得下別的請求。

    ⚠️ **必須用 `with TestClient(app) as client:`**（審查抓到的第 12 個假測試）：
    `starlette/testclient.py` 的 `_portal_factory` 只有在 `__enter__` 設過
    `self.portal` 時才會讓同一個 client 的所有請求共用**同一個**事件迴圈；否則
    每次 `.get()`／`.post()` 各自 `start_blocking_portal()`，等於各自開一個全新
    的事件迴圈執行緒——`/probe` 因此永遠跑在與被卡住的請求完全無關的迴圈上，
    不管閘門的等待有沒有誤放在事件迴圈上，這條測試都會通過。已用 mutation 驗證：
    把 `run_in_threadpool(_run_with_admission)` 換成直接呼叫 `_run_with_admission()`
    （brief 明文警告過的錯誤），在沒有 `with` 時這條測試依然 PASS。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _BlockingAsr()
    admission = TurnAdmission(1, queue_timeout=5.0)
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

    @app.get("/probe")
    def probe() -> dict:
        return {"ok": True}

    app.include_router(
        create_app_turns_router(
            accounts=svc,
            pipeline=pipeline,
            gate=ConsentGate(svc),
            voice=VoiceReplyDelivery(None, include_text=True),
            new_id=lambda: "trace-1",
            clock=lambda: NOW,
            admission=admission,
        ),
        prefix="/api/v1",
    )

    with TestClient(app) as client:

        def send_first() -> None:
            _post_audio(client, token)

        def send_second() -> None:
            _post_audio(client, token, body=b"\x00second-audio")

        t1 = threading.Thread(target=send_first)
        t1.start()
        assert asr.entered.wait(5.0), "第一個請求應該已經進到辨識裡、正持有名額"

        t2 = threading.Thread(target=send_second)
        t2.start()
        deadline = time.monotonic() + 2.0
        while admission.waiting() == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert admission.waiting() == 1, "第二個請求應該已經卡在閘門的排隊等待裡"

        start = time.monotonic()
        res = client.get("/probe")
        elapsed = time.monotonic() - start
        assert res.status_code == 200
        assert elapsed < 1.0, f"/probe 被閘門的排隊等待卡住了，耗時 {elapsed} 秒"

        asr.release.set()
        t1.join(5.0)
        t2.join(5.0)
        assert not t1.is_alive()
        assert not t2.is_alive()


def test_每分鐘輪數保險絲觸發時回_429_而不是靜默丟掉():
    """對真人操作等同無限，但前端重連迴圈狂送時不能任由它一路打穿到 GPU。"""

    class _DenyingRateLimiter:
        def hit(self, key: str) -> bool:
            return False

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _admission_client(
        svc, asr=MockAsrClient("阿公早安"), rate_limiter=_DenyingRateLimiter()
    )
    res = _post_audio(client, token)
    assert res.status_code == 429
    body = res.json()
    assert body["error"]["code"] == "too_many_requests"
    assert "還在忙" in body["error"]["message"]


def test_節流放行時不受影響_對真人操作等同無限_over_rest():
    """一律放行的節流器不該讓既有行為變樣——保險絲對真人操作必須是無感的。"""

    class _AllowingRateLimiter:
        def hit(self, key: str) -> bool:
            return True

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _admission_client(
        svc, asr=MockAsrClient("阿公早安"), rate_limiter=_AllowingRateLimiter()
    )
    res = _post_audio(client, token)
    assert res.status_code == 201
