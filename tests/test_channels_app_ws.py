"""App 對講機 WebSocket 通道測試（spec 2026-07-28 P2）。

守的是三件事：
1. **認證與同意複核不可省**——token 不代表同意，撤回或綁定消失即擋。
2. **安撫話在工具跑之前就送出**，且對話路徑上不合成、不上傳（只查表）。
3. **一輪失敗不可打斷整條連線**——長輩不必重新開 App。
"""

from __future__ import annotations

import json
import threading
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
from kinsun.channels.app.ws import create_app_ws_router
from kinsun.channels.inbound import VoiceReplyDelivery
from kinsun.llm import Message, ToolCall, ToolSpec, ToolTurn
from kinsun.locations.store import ElderLocation
from kinsun.personas import DEFAULT_PERSONA_ID
from kinsun.pipeline import VoicePipeline
from kinsun.safety.detector import RiskDetector
from kinsun.speech.ack_audio import AckClip
from kinsun.speech.asr import ASRError, MockAsrClient
from kinsun.speech.chunking import split_for_speech
from kinsun.speech.tts import TTSError, TtsResult
from kinsun.tools.registry import ToolRegistry
from tests.fakes import FakeAccountStore, FakeLocationStore, FakeRiskEventStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=TPE)


class _EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].content}"


#: 切得出三句的回覆（每句皆 ≥ MIN_CHUNK_CHARS＝8 字）。抽成常數是為了讓續段測試能
#: 拿它去跑 `split_for_speech`，斷言「推出去的段落＝管線切出來的段落」而不是抄一份字面值。
_MULTI_SENTENCE_REPLY = "第一句話夠長可以自成一段。第二句話也夠長可以自成一段。第三句話同樣夠長。"


class _MultiSentenceLLM:
    """回一段切得出三句的回覆，供續段測試用。每句皆 ≥ MIN_CHUNK_CHARS（8 字）。"""

    def generate(self, *, system_prompt, messages, response_schema=None):
        return _MULTI_SENTENCE_REPLY


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
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str) -> TtsResult:
        self.calls.append(text)
        return TtsResult(text=text, audio=b"fake-m4a", duration_ms=1200)


class _TextOnlyTts:
    """TTS 失敗退純文字的替身（audio=None）：C1 的內嵌路徑不該被走到。"""

    def synthesize(self, text: str) -> TtsResult:
        return TtsResult(text=text, audio=None)


class _FailAfterFirstTts:
    """第一次合成成功（那是回覆的第一段），第二次起擲 TTSError。"""

    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str) -> TtsResult:
        self.calls += 1
        if self.calls > 1:
            raise TTSError("模擬合成失敗")
        return TtsResult(text=text, audio=b"fake-m4a", duration_ms=1200)


class _FailAfterSecondTts:
    """第一、二次合成成功（回覆第一段＋續段第一段），第三次起擲 TTSError。

    與 `_FailAfterFirstTts`（續段第一次疊代就失敗）刻意不同：這裡要讓續段迴圈
    **先成功推出一段，下一段才失敗**——這是 `sent_terminator` 這個旗標唯一測得出
    「送過一段就誤當成已經送過終止訊框」這種寫錯方式的情境（`_FailAfterFirstTts`
    因為迴圈第一次疊代就 break，永遠不會走到「送出成功續段」那一行）。
    """

    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str) -> TtsResult:
        self.calls += 1
        if self.calls > 2:
            raise TTSError("模擬合成失敗（跑到一半才炸）")
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
        # 這一輪被要求用哪一種人設的句子（2026-08-05）——人設由 agent 隨通知帶到
        # 這裡，WS 端不查資料庫，故它是唯一能證明接線沒斷的地方。
        self.personas: list[str] = []
        self._clip = clip or AckClip(
            text="好，我幫您看看最近的新聞喔",
            audio_url="https://cdn.example/ack.m4a",
            duration_ms=1300,
        )

    def clip_for(self, tool_name: str, *, persona_id: str = DEFAULT_PERSONA_ID) -> AckClip | None:
        self.asked.append(tool_name)
        self.personas.append(persona_id)
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
    admission=None,
    rate_limiter=None,
    show_transcript=False,
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
            voice=VoiceReplyDelivery(
                publisher or _FakePublisher(),
                include_text=True,
                show_transcript=show_transcript,
            ),
            ack_audio=ack_audio,
            locations=locations,
            new_id=lambda: "turn-1",
            clock=lambda: NOW,
            admission=admission,
            rate_limiter=rate_limiter,
            tts=tts or _VoiceTts(),
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def _receive_frame(ws) -> dict:
    """收一個下行 frame，JSON 與 binary（內嵌音檔，C1）都吃。

    binary frame 的 header 攤成一般的 dict 回傳，音檔本體放在 `audio` 鍵——這樣既有
    的斷言（`frame["type"]`／`frame["text"]`）一字不必改，新增的斷言看得到音檔。
    協定見 `channels/app/ws.py` 模組 docstring。
    """
    message = ws.receive()
    if message.get("text") is not None:
        return json.loads(message["text"])
    raw = message["bytes"]
    header_length = int.from_bytes(raw[:4], "big")
    header = json.loads(raw[4 : 4 + header_length].decode("utf-8"))
    return {**header, "audio": raw[4 + header_length :]}


def _frames(ws, count_wanted: int) -> list[dict]:
    return [_receive_frame(ws) for _ in range(count_wanted)]


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
        reply = _receive_frame(ws)
    assert reply["type"] == "reply"
    assert reply["turn_id"] == "turn-1"
    assert "今天有什麼新消息" in reply["text"]
    assert reply["duration_ms"] == 1200


# ── 音檔隨 binary frame 直送（2026-07-30 延遲優化 C1）────────────────────


def test_reply_audio_rides_the_same_frame_so_the_app_never_downloads_it():
    """⭐ 這一刀的全部價值：音檔本體就在 frame 裡，App 不必再向 Supabase 下載一趟。

    `audio_url` 刻意留空——留著它等於邀請 App 去下載，那正是要省掉的那一趟。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
    assert reply["audio"] == b"fake-m4a"
    assert reply["audio_url"] == ""


def test_the_audio_is_pushed_before_the_archival_upload_runs():
    """順序即價值：長輩先聽到聲音，存證上傳排在後面。

    反過來（先上傳再推）等於白做這一刀——長輩照樣要等完那 0.54 秒（尖峰 2.37 秒）。

    ⚠️ 量法刻意不是「兩件事各記一筆時間戳再比大小」：那要從客戶端觀測伺服器端的順序，
    而「送出完成」與「測試收到」之間有排程空窗，上傳可能在空窗裡插進來——第一版就是
    這樣寫的，會偶發紅燈。改成**讓上傳卡住**：若音檔是在上傳之後才推的，這裡就永遠
    收不到訊框而逾時失敗；收到了就證明推送確實排在上傳之前。
    """
    upload_started = threading.Event()
    release_upload = threading.Event()

    class _BlockingPublisher(_FakePublisher):
        def publish(self, audio: bytes, *, content_type: str) -> str:
            upload_started.set()
            release_upload.wait(timeout=5)
            return super().publish(audio, content_type=content_type)

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, publisher=_BlockingPublisher())
    try:
        with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
            ws.send_bytes(b"\x00fake-audio")
            # 上傳被卡住（或還沒輪到它跑），卻已經收到音檔＝推送排在上傳之前。
            frame = _receive_frame(ws)
            assert frame["audio"] == b"fake-m4a"
            # ⚠️ 這一行必須是 `wait` 而不是 `is_set`：收到訊框的那一刻，工作執行緒可能
            # 還沒走到上傳那一行——而那正是我們要的順序，不是缺陷。
            assert upload_started.wait(timeout=5), "存證上傳始終沒被呼叫，後台將無回放"
    finally:
        release_upload.set()


def test_archival_upload_failure_does_not_cost_the_elder_the_reply():
    """存證上傳失敗只是後台少一筆回放——長輩已經收到音檔，這一輪對他完全成功。

    ⚠️ 與非內嵌那條路刻意不同：那裡上傳失敗等於長輩什麼都拿不到，所以必須退回文字。
    """

    class _BoomPublisher:
        def publish(self, audio: bytes, *, content_type: str) -> str:
            raise RuntimeError("Supabase 掛了")

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, publisher=_BoomPublisher())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)

    assert reply["type"] == "reply"
    assert reply["audio"] == b"fake-m4a"


def test_a_text_only_turn_still_arrives_as_a_json_frame():
    """TTS 失敗退純文字時沒有音檔可內嵌，照舊走 JSON frame——App 兩種都要能收。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, tts=_TextOnlyTts())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
    assert reply["type"] == "reply"
    assert "audio" not in reply  # 純 JSON frame
    assert reply["audio_url"] == ""


def test_the_elder_never_gets_two_replies_for_one_turn():
    """音檔 frame 推出去之後不可再補一則 JSON reply——播放佇列會把同一句話唸兩次。

    ⚠️ 單段回覆現在也會多送一個續段終止訊框（2026-08-01，見 `_push_continuation_chunks`）
    ——每輪要收 2 個 frame 才不會把上一輪沒收乾淨的終止訊框誤當成下一輪的 reply。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        first, _terminator = _frames(ws, 2)
        # 再送一輪；若上一輪補了第二則 reply，這裡收到的會是它而不是新一輪的。
        ws.send_bytes(b"\x00second-audio")
        second, _terminator2 = _frames(ws, 2)
    assert first["type"] == "reply"
    assert second["type"] == "reply"
    assert second["audio"] == b"fake-m4a"


# ── 續段語音直送（2026-08-01）────────────────────────────────────────────


def test_continuation_chunks_are_pushed_in_order():
    """第一段之後，剩餘段落逐一以 binary frame 推出，index 遞增、最後一段 is_last。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, llm=_MultiSentenceLLM())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"elder-audio")
        frames = _frames(ws, 3)  # reply ＋ chunk1 ＋ chunk2

    chunks = [f for f in frames if f["type"] == "chunk"]
    assert [c["index"] for c in chunks] == [1, 2]
    assert [c["is_last"] for c in chunks] == [False, True]
    # ⚠️ 併發之下前端靠 turn_id 歸屬，錯了會把 A 的段接到 B 後面（同 459051f 那類錯亂）
    assert {c["turn_id"] for c in chunks} == {"turn-1"}  # _client 的 new_id 固定回 turn-1
    assert chunks[0]["text"] == "第二句話也夠長可以自成一段。"
    assert chunks[0]["audio"] == b"fake-m4a"  # _VoiceTts 的固定音檔


def test_chunks_come_from_the_real_reply_not_the_debug_display_string():
    """⭐ 續段切的必須是**真正的回覆文字**，不是投遞層的顯示字串（審查 Critical 1）。

    ⚠️ 這條與 `test_continuation_chunks_are_pushed_in_order` 的差別只有一個開關：
    `show_transcript=True`（`.env` 上這台機器目前就是 `ASR_DEBUG_SHOW_TRANSCRIPT=true`）。
    那個模式下 `inbound.py::_compose_text` 回的是「辨識：…\\n\\n回復：…」，拿它去
    `split_for_speech` 會多切出一段「辨識：…」，於是**第一句被當成續段再唸一次**，
    而且「回復：」三個字會被 TTS 唸出來：

        pipeline 切（真回覆）：['第一句話…。', '第二句話…。', '第三句話同樣夠長。']
        顯示字串切：          ['辨識：…\\n\\n', '回復：第一句話…。', '第二句話…。', ...]

    斷言刻意寫成「＝`split_for_speech(真回覆)[1:]`」而不是抄一份字面值：兩邊必須是
    同一個純函式的同一組輸出，這正是段落對得起來的定義（`chunking.py::reply_digest`
    的警告寫的是同一個坑，2026-07-26 實機驗證踩過一次）。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, llm=_MultiSentenceLLM(), show_transcript=True)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"elder-audio")
        frames = _frames(ws, 3)  # reply ＋ chunk1 ＋ chunk2

    reply = frames[0]
    # 先證明這條測試真的踩在那個分岔上——沒有這一行，show_transcript 被忽略也照樣全綠。
    assert reply["text"].startswith("辨識："), "debug 顯示前綴沒出現，本測試沒有鑑別力"
    chunks = [f for f in frames if f["type"] == "chunk"]
    assert [c["text"] for c in chunks] == split_for_speech(_MULTI_SENTENCE_REPLY)[1:]
    assert all("回復：" not in c["text"] for c in chunks), "投遞層前綴被唸給長輩聽了"


def test_single_segment_reply_pushes_no_audio_chunk():
    """短回覆切不出第二段——不推任何**帶音檔**的續段訊框。

    ⚠️ 仍會收到一個空音檔的終止訊框：前端靠 is_last 結束該輪，缺了會把該輪當成
    還沒結束（見 spec §5.2）。故此處收兩個訊框而不是一個。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)  # _EchoLLM 回短句
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"elder-audio")
        frames = _frames(ws, 2)  # reply ＋ 終止訊框

    audio_chunks = [f for f in frames if f["type"] == "chunk" and f["audio"]]
    assert audio_chunks == []


def test_chunk_synthesis_failure_still_sends_terminator():
    """續段合成失敗 → 補送空音檔的 is_last 訊框，前端才不會把該輪當成還沒結束。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, llm=_MultiSentenceLLM(), tts=_FailAfterFirstTts())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"elder-audio")
        frames = _frames(ws, 2)  # reply ＋ 終止訊框

    terminator = frames[-1]
    assert terminator["type"] == "chunk"
    assert terminator["is_last"] is True, "無論如何都要有終止訊號"
    assert terminator["text"] == "", "終止訊框不帶文字"
    assert terminator["audio"] == b"", "終止訊框不帶音檔"


def test_chunk_synthesis_failure_after_a_successful_chunk_still_sends_terminator():
    """續段先成功推出一段、下一段才失敗——仍要補送終止訊框，不能因為「已經送過一段」就當作結束。

    ⚠️ 這是 `sent_terminator` 唯一測得出「把『送過一段』誤當成『已經送過終止訊框』」
    這種寫錯方式的情境：`test_chunk_synthesis_failure_still_sends_terminator` 用的
    `_FailAfterFirstTts` 在續段迴圈第一次疊代就失敗，永遠不會走到「成功送出一段」
    那一行，測不出這條路（已用 mutation 驗證：把 `sent_terminator = is_last` 改成
    `sent_terminator = True`，那條測試仍然通過，只有這條會變紅——見 task-3-report.md）。
    """
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, llm=_MultiSentenceLLM(), tts=_FailAfterSecondTts())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"elder-audio")
        frames = _frames(ws, 3)  # reply ＋ 成功的續段（index 1）＋ 終止訊框

    chunks = [f for f in frames if f["type"] == "chunk"]
    assert len(chunks) == 2, "應收到一段成功的續段，加上一個終止訊框"
    successful, terminator = chunks
    assert successful["index"] == 1
    assert successful["audio"] == b"fake-m4a", "成功的那一段必須帶音檔"
    assert successful["is_last"] is False, "它不是回覆的最後一段，不該自己帶 is_last"
    assert terminator["is_last"] is True, "無論如何都要有終止訊號"
    assert terminator["text"] == "", "終止訊框不帶文字"
    assert terminator["audio"] == b"", "終止訊框不帶音檔"


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
    # 人設有跟著送到語庫（2026-08-05）：這一輪沒有設定人設，故為預設。
    assert ack_audio.personas == [DEFAULT_PERSONA_ID]
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
        reply = _receive_frame(ws)
    assert reply["type"] == "reply"


def test_no_ack_when_no_tool_is_called():
    """整輪沒有工具呼叫就沒有安撫話（語料實測 5.5% 的輪次如此）。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    ack_audio = _FakeAckAudio()
    client = _client(svc, ack_audio=ack_audio)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
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
        _receive_frame(ws)
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
        _receive_frame(ws)
    assert locations.get_for_elder(elder.elder_id) is None


def test_malformed_location_frame_does_not_kill_the_connection():
    """外部輸入是資料不是指令：一則畸形訊息只該被丟掉，不可切斷長輩的連線。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text("這不是 JSON {{{")
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
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
        first = _receive_frame(ws)
        # 連線還活著：再送一輪照樣有回應。
        ws.send_bytes(b"\x00fake-audio")
        second = _receive_frame(ws)
    assert first["type"] in {"reply", "error"}
    assert second["type"] in {"reply", "error"}


def test_oversized_audio_is_rejected_without_closing_the_connection():
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"x" * (10 * 1024 * 1024 + 1))
        frame = _receive_frame(ws)
        assert frame["type"] == "error"
        ws.send_bytes(b"\x00fake-audio")
        assert _receive_frame(ws)["type"] == "reply"


# ── 併發輪（spec 2026-07-28 P3）────────────────────────────────────────


class _SlowLLM:
    """卡在 gate 上的 LLM——用來把一輪留在「進行中」的狀態。"""

    def __init__(self, gate, reply: str = "答案來了") -> None:
        self._gate = gate
        self._reply = reply

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        self._gate.wait(timeout=5)
        return self._reply


class _RecordingSession:
    """記下每一輪 assemble 拿到的 history，用來驗在途上下文有沒有進去。"""

    def __init__(self) -> None:
        self.histories: list[list[str]] = []
        self.prompts: list[str] = []

    def assemble(self, elder_id, query):
        from types import SimpleNamespace

        from kinsun.turn_context import current_pending_utterances

        history = [Message("user", t) for t in current_pending_utterances()]
        self.histories.append([m.content for m in history])
        return SimpleNamespace(system_suffix="", history=history)

    def record_turn(self, elder_id, *messages, at=None):
        pass


def test_too_many_concurrent_turns_gets_a_busy_reply_not_silence():
    """長輩連按會開出無限多輪。婉拒要**講出來**——靜默丟掉他會以為金孫壞了。"""
    import threading as _t

    gate = _t.Event()
    svc = _service()
    _, token = _bound_elder_token(svc)
    ids = (f"turn-{i}" for i in count(1))
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(_SlowLLM(gate), _NullSession()),
        tts=_VoiceTts(),
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
            voice=VoiceReplyDelivery(_FakePublisher(), include_text=True),
            new_id=lambda: next(ids),
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        for _ in range(4):  # 上限 3，第四次應被婉拒
            ws.send_bytes(b"\x00fake-audio")
        busy = _receive_frame(ws)
        assert busy["type"] == "error"
        assert "還在忙" in busy["text"]
        gate.set()
        # 前三輪照樣各自回答，沒有被第四次影響。
        # ⚠️ 收 6 個訊框：每一輪除了 reply 還會補一個續段終止訊框（`_SlowLLM` 的
        # 「答案來了」切不出第二段），而三輪的訊框會交錯抵達，不能假設它們成對出現
        # ——故收滿再依 type 過濾（2026-08-01：終止訊框改成連 `tts` 未注入時也照送，
        # 這一輪的訊框序列因此與正式環境一致了）。
        frames = _frames(ws, 6)
    assert [f["type"] for f in frames if f["type"] == "reply"] == ["reply"] * 3


def test_a_second_question_sees_the_first_one_still_in_flight():
    """⭐ 併發對話的核心：長輩問完新聞、接著問「那天氣呢」，第二輪組裝情境時
    必須看得到第一句——否則「那」沒有指涉對象，模型只能反問。"""
    import threading as _t

    gate = _t.Event()
    svc = _service()
    _, token = _bound_elder_token(svc)
    session = _RecordingSession()
    ids = (f"turn-{i}" for i in count(1))
    pipeline = VoicePipeline(
        asr=MockAsrClient("今天有什麼新消息"),
        agent=CareAgent(_SlowLLM(gate), session),
        tts=_VoiceTts(),
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
            voice=VoiceReplyDelivery(_FakePublisher(), include_text=True),
            new_id=lambda: next(ids),
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00first")
        # 等第一輪確實登記進在途清單（它卡在 gate 上）。
        for _ in range(500):
            if session.histories:
                break
            _t.Event().wait(0.01)
        ws.send_bytes(b"\x00second")
        for _ in range(500):
            if len(session.histories) >= 2:
                break
            _t.Event().wait(0.01)
        gate.set()
        [_receive_frame(ws) for _ in range(2)]
    assert session.histories[0] == [], "第一輪不該看到自己"
    assert session.histories[1] == ["今天有什麼新消息"], (
        f"第二輪沒看到在途的第一句：{session.histories}"
    )


def test_a_turn_leaves_the_in_flight_list_once_its_answer_is_out():
    """⭐ 答案已經送到長輩耳朵的那一輪，不可以還掛在「正在處理中」的清單上
    （2026-08-01 全分支審查 Important 1）。

    失效情境：A 的回覆已推出（此時 `_settle_memory_write` 保證 A 已寫進 `turns`），
    但續段還要推 7～10 秒。若 `in_flight.finish` 等到續段跑完才做，長輩這段期間
    插嘴問 B 時，B 的情境會同時看到——
      - `shortterm.recent()`：A 的問句＋金孫的回答（配對完整）
      - `current_pending_utterances()`：**又**把 A 的問句附在歷史尾巴
    模型於是看到 `user:A / assistant:A答 / user:A / user:B`，一個已經回答過的問題
    被當成還沒回答、還擺在最新位置。`turn_context.pending_utterances` 的定義是
    「還有哪些話**正在處理中**」，答案已入耳的那一句不該還在裡面。

    ⚠️ 時序靠事件釘死、不靠 sleep：續段的第一次合成卡住之後才送第二輪，所以
    「A 已經在推續段」在 B 組裝情境的當下必然成立——這正是要驗的那一刻。
    """
    import threading as _t

    class _BlockingChunkTts:
        """router 層的續段 TTS：第一次合成就卡住，把 A 釘在「正在推續段」的狀態。"""

        def __init__(self) -> None:
            self.entered = _t.Event()
            self.release = _t.Event()

        def synthesize(self, text: str) -> TtsResult:
            self.entered.set()
            self.release.wait(timeout=5)
            return TtsResult(text=text, audio=b"fake-m4a", duration_ms=1200)

    chunk_tts = _BlockingChunkTts()
    svc = _service()
    _, token = _bound_elder_token(svc)
    session = _RecordingSession()
    ids = (f"turn-{i}" for i in count(1))
    pipeline = VoicePipeline(
        asr=MockAsrClient("今天有什麼新消息"),
        agent=CareAgent(_MultiSentenceLLM(), session),
        tts=_VoiceTts(),  # 第一段照常合成（不卡），卡的是 router 層的續段
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
            voice=VoiceReplyDelivery(_FakePublisher(), include_text=True),
            new_id=lambda: next(ids),
            clock=lambda: NOW,
            tts=chunk_tts,
        ),
        prefix="/api/v1",
    )
    client = TestClient(app)
    try:
        with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
            ws.send_bytes(b"\x00first")
            assert chunk_tts.entered.wait(timeout=5), "第一輪沒有走到續段，這條測試沒驗到東西"
            ws.send_bytes(b"\x00second")
            for _ in range(500):
                if len(session.histories) >= 2:
                    break
                _t.Event().wait(0.01)
            chunk_tts.release.set()
            _receive_frame(ws)  # 第一輪的 reply（其餘訊框不影響斷言）
    finally:
        chunk_tts.release.set()  # 斷言失敗時也要放掉，別讓工作執行緒卡滿逾時
    assert len(session.histories) >= 2, f"第二輪沒有組裝情境：{session.histories}"
    assert session.histories[1] == [], (
        f"第一輪的答案已經送出去了，卻還掛在在途清單上：{session.histories}"
    )


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"location": 123, "latitude": 22.99, "longitude": 120.21}, "地名是數字"),
        ({"location": ["台南市"], "latitude": 22.99, "longitude": 120.21}, "地名是陣列"),
        ({"location": {"n": "台南"}, "latitude": 22.99, "longitude": 120.21}, "地名是物件"),
        ({"location": "台南市", "latitude": "北緯22", "longitude": 120.21}, "緯度是字串"),
        ({"location": "台南市", "latitude": 22.99, "longitude": [120.21]}, "經度是陣列"),
    ],
)
def test_wrong_typed_location_frame_does_not_kill_the_connection(payload, why):
    """型別不合的位置訊框只該被丟掉（V-03，2026-07-29）。

    ⚠️ 這個 bug 的陰險之處是**發作時機**：位置訊框只是存進 pending，直到長輩
    **下一次開口**送音檔才會用到。所以症狀是「講完一整句話，連線斷掉，那句話也
    沒進庫」——長輩以為金孫壞了，後台完全查不到原因。而且只要 App 某個版本送錯
    型別，該版本**所有使用者**的第一句話都會斷線。

    故斷言的是「音檔送得出去、回覆收得到」，不只是「解析函式沒拋例外」。
    """
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps(payload))
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
    assert reply["type"] == "reply", why
    assert locations.get_for_elder(elder.elder_id) is None, why


def test_a_good_location_frame_after_a_bad_one_still_works():
    """壞訊框不可污染後續：丟掉那一筆之後，下一筆正常的位置仍要寫得進去。"""
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": 123, "latitude": 22.99, "longitude": 120.21}))
        ws.send_text(json.dumps({"location": "台南市", "latitude": 22.99, "longitude": 120.21}))
        ws.send_bytes(b"\x00fake-audio")
        _receive_frame(ws)
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "台南市", NOW.timestamp(), 22.99, 120.21
    )


def test_boolean_coordinates_are_rejected_rather_than_coerced_to_one():
    """bool 是 int 的子型別，float(True)＝1.0——會把長輩寫到外海去，必須擋。"""
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": "台南市", "latitude": True, "longitude": 120.21}))
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
    assert reply["type"] == "reply"
    assert locations.get_for_elder(elder.elder_id) is None


@pytest.mark.parametrize(
    ("lat", "lon", "why"),
    [
        (999, 120.21, "緯度 999"),
        (-999, 120.21, "緯度 -999"),
        (22.99, 999, "經度 999"),
        (90.1, 120.21, "緯度剛好越界"),
    ],
)
def test_out_of_range_coordinates_are_not_written(lat, lon, why):
    """座標超出地表範圍＝這輪沒有位置（V-04，2026-07-29）。

    原樣落庫的代價不是「一筆髒資料」：`LocationFacts` 會把它注入每一輪的提示詞，
    附近地點搜尋會拿它當圓心去撈——長輩問「附近有沒有藥局」，答案是北極圈的。
    """
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": "台南市", "latitude": lat, "longitude": lon}))
        ws.send_bytes(b"\x00fake-audio")
        reply = _receive_frame(ws)
    assert reply["type"] == "reply", why
    assert locations.get_for_elder(elder.elder_id) is None, why


def test_boundary_coordinates_are_accepted():
    """±90／±180 是合法座標，不可連邊界一起擋掉。"""
    svc = _service()
    elder, token = _bound_elder_token(svc)
    locations = FakeLocationStore()
    client = _client(svc, locations=locations)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_text(json.dumps({"location": "北極點", "latitude": 90.0, "longitude": 180.0}))
        ws.send_bytes(b"\x00fake-audio")
        _receive_frame(ws)
    assert locations.get_for_elder(elder.elder_id) == ElderLocation(
        elder.elder_id, "北極點", NOW.timestamp(), 90.0, 180.0
    )


# ── binary frame 編碼（C1 協定）─────────────────────────────────────────


def test_encode_reply_frame_round_trips_with_chinese_and_hostile_audio_bytes():
    """長度前綴而非分隔符：音檔內容可以是任何位元組，掃分隔符遲早會被炸掉。

    這裡刻意讓音檔本身含有 `}`、換行與 header 的片段。
    """
    from kinsun.channels.app.ws import encode_reply_frame

    header = {"type": "reply", "turn_id": "t1", "text": "阿公早安，今天天氣不錯喔"}
    audio = b'}\n{"type": "reply"}\x00\xff'

    raw = encode_reply_frame(header, audio)

    header_length = int.from_bytes(raw[:4], "big")
    assert json.loads(raw[4 : 4 + header_length].decode("utf-8")) == header
    assert raw[4 + header_length :] == audio


def test_encode_reply_frame_keeps_chinese_readable_rather_than_escaped():
    """`ensure_ascii=False`：header 直接是 UTF-8，不必讓 App 解 \\uXXXX。"""
    from kinsun.channels.app.ws import encode_reply_frame

    raw = encode_reply_frame({"text": "阿公"}, b"")

    assert "阿公".encode() in raw


# ── 容量閘門（spec 2026-07-30 §10 B2）──────────────────────────────────


class _BlockingAsr:
    """卡在辨識裡不出來的 ASR：用來讓第一輪一直佔著名額。"""

    def __init__(self, transcript: str = "今天有什麼新消息") -> None:
        self._transcript = transcript
        self.entered = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        self.entered.set()
        self.release.wait(5.0)
        return self._transcript


def test_併發超過上限時先送排隊訊框_不靜默丟掉那句話():
    """⚠️ 靜默排隊與當機在畫面上長得一模一樣。長輩只會覺得金孫不理他，然後
    再講一次——那會讓已經滿載的 GPU 雪上加霜。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _BlockingAsr()
    client = _client(svc, asr=asr, admission=TurnAdmission(1, queue_timeout=5.0))
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        assert asr.entered.wait(5.0), "第一輪應該已經進到辨識裡"
        ws.send_bytes(b"audio-2")
        frame = _receive_frame(ws)
        assert frame["type"] == "queued"
        # ⚠️ position 是排隊名次（1-based），不是「前面還有幾位」——這裡剛好
        # limit=1 讓兩種說法數值相同，正式環境 limit=6 時就會不相等（見
        # ws.py 模組 docstring／06 §5 的更正說明）。
        assert frame["position"] == 1, "應該排隊第 1 位"
        asr.release.set()


def test_名額夠時不送排隊訊框_不要嚇沒有在等的人():
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, admission=TurnAdmission(2, queue_timeout=5.0))
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        frame = _receive_frame(ws)
        assert frame["type"] != "queued"


def test_排隊逾時回一句人話_不是靜默也不是裸錯():
    """長輩看不懂 429，也等不到一個永遠不會來的回應。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _BlockingAsr()
    client = _client(svc, asr=asr, admission=TurnAdmission(1, queue_timeout=0.2))
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        assert asr.entered.wait(5.0)
        ws.send_bytes(b"audio-2")
        assert _receive_frame(ws)["type"] == "queued"
        timeout_frame = _receive_frame(ws)
        assert timeout_frame["type"] == "error"
        # 是人話不是狀態碼；文字內容沿用本檔既有的「還在忙」婉拒文案（`_BUSY_REPLY`），
        # 而不是管線一般性失敗的 `SYSTEM_TROUBLE_REPLY`——兩者都是「人話」、都不含
        # 「429」，只看這兩條斷言測不出 `AdmissionTimeout` 是否被接到正確的分支
        # （已用 mutation 驗證：把 `except AdmissionTimeout` 拿掉、讓它落進泛用的
        # `except Exception`，這兩條斷言仍然通過）。
        assert timeout_frame["text"]
        assert "429" not in timeout_frame["text"]
        assert "還在忙" in timeout_frame["text"]
        asr.release.set()


def test_名額在一輪失敗時也要釋放():
    """⚠️ 管線炸掉時若沒釋放名額，那個名額就永久消失；漏到滿之後所有人從此
    排隊，而伺服器看起來完全健康。

    ⚠️ **這裡刻意讓兩輪真的重疊**（第一輪炸掉之前，第二輪已經真的排上隊）：
    brief 原始版本是「先送第一輪、等它完全結束（拿到 reply／error）才送第二輪」，
    兩輪之間毫無時間重疊——那種寫法下即使閘門完全沒接上（例如忘了寫 `with`，
    見 `admission.py` docstring 的警告），`active()` 從頭到尾都是 0、
    `second["type"] != "queued"` 也照樣成立，測試一樣全綠但完全沒測到「例外
    釋放」這件事（已用 mutation 驗證：把 `with turn_gate.admit(...)` 換成
    `contextlib.nullcontext()` 整段繞過閘門，brief 原始版本的斷言仍然通過）。
    改成「第一輪持有名額時炸掉、第二輪已經真的在排隊」才能證明例外真的觸發了
    閘門的釋放路徑，而不只是連線沒被打斷。

    ⚠️ 刻意拋 `RuntimeError` 而非 `ASRError`：`channels/inbound.py::_run_pipeline`
    把 `ASRError`／`LLMError`／`MemoryStoreError` 三種**內部就地接住**、改送回退
    語音（`voice.deliver_standby`）後正常回傳，例外根本不會冒出 `dispatch()`，
    `_run_turn` 也就走不到 `except Exception` 那支——沿用 brief 原本的 `ASRError`
    只會測到「回退話術」這條既有路徑（`test_a_failing_turn_...` 已經測過），
    測不到閘門在**未預期例外**時是否正確釋放。
    """

    class _ExplodingAsr:
        """卡住直到被釋放、釋放後拋出管線不會就地接住的例外（模擬持有名額時真的炸掉）。"""

        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio: bytes, *, content_type: str) -> str:
            self.entered.set()
            self.release.wait(5.0)
            raise RuntimeError("這一輪炸了（非 ASRError，管線不會就地接住）")

    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _ExplodingAsr()
    admission = TurnAdmission(1, queue_timeout=5.0)
    client = _client(svc, asr=asr, admission=admission)
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        assert asr.entered.wait(5.0), "第一輪應該已經進到辨識裡、正持有名額"
        ws.send_bytes(b"audio-2")
        queued = _receive_frame(ws)
        assert queued["type"] == "queued", "第二輪必須真的排上隊，才測得到釋放"
        assert queued["position"] == 1
        asr.release.set()
        # 順序不保證（兩輪炸掉後各自送 error 是真併發，先後由排程決定）：
        # 只斷言兩則都收得到、都是 error，沒有人卡在排隊或逾時。
        remaining = {_receive_frame(ws)["type"] for _ in range(2)}
    assert remaining == {"error"}, "兩輪都該回錯誤訊框，不該有人卡在排隊或逾時"
    assert admission.active() == 0


# ── 每位長輩的輪數保險絲（spec 2026-07-30 §10 B2）──────────────────────
#
# ⚠️ brief 本身沒有給這一段的測試案例（只給了容量閘門四條）；`rate_limiter` 是
# 這一輪額外接的另一個對外行為（每分鐘輪數保險絲），沒有測試會是接線但沒人守。


class _DenyingRateLimiter:
    """一律回絕的節流器替身：不必真的一分鐘打 31 次，就能確認保險絲真的接上。"""

    def hit(self, key: str) -> bool:
        return False


def test_每分鐘輪數保險絲觸發時回一句人話_不是靜默丟掉():
    """對真人操作等同無限，但前端重連迴圈狂送時不能任由它一路打穿到 GPU。"""
    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, rate_limiter=_DenyingRateLimiter())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        frame = _receive_frame(ws)
    assert frame["type"] == "error"
    assert "還在忙" in frame["text"]


def test_節流放行時不受影響_對真人操作等同無限():
    """一律放行的節流器不該讓既有行為變樣——保險絲對真人操作必須是無感的。"""

    class _AllowingRateLimiter:
        def hit(self, key: str) -> bool:
            return True

    svc = _service()
    _, token = _bound_elder_token(svc)
    client = _client(svc, rate_limiter=_AllowingRateLimiter())
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"\x00fake-audio")
        frame = _receive_frame(ws)
    assert frame["type"] == "reply"


def test_排隊訊框送出用較短逾時_不拖住全域入場(monkeypatch):
    """⚠️ 審查發現：`on_queued` 被呼叫當下，這個號碼已經**在佇列裡**（取號在鎖內
    完成），此刻佇列非空，代表**任何人**嘗試 `admit()`（不管有沒有空位）都會被
    逼進佇列、等這通回呼結束才恢復正常——一支訊號不良的手機（送出被 TCP 背壓
    卡住）可讓全域入場停擺到 `_Sender.send` 的逾時值。`notify_queued` 因此改傳
    `timeout=1.0`（而非 `send` 給其他訊框用的預設 5.0），把曝險窗縮到五分之一。

    這裡直接記錄 `_Sender.send` 實際被呼叫時的 `timeout` 值——比起端到端量測
    「卡住的連線讓全域入場慢了幾秒」（需要精準控制兩個獨立連線的時序，容易
    flaky），直接釘住這個實作選擇更穩定，且正是回歸時最容易被悄悄改掉的地方
    （例如有人「順手」把 `timeout=1.0` 又改回省略、退回預設 5 秒）。
    """
    from kinsun.channels.app.ws import _Sender

    calls: list[tuple[str, float]] = []
    original_send = _Sender.send

    def _spy_send(self, payload, *, timeout=5.0):
        calls.append((payload.get("type"), timeout))
        return original_send(self, payload, timeout=timeout)

    monkeypatch.setattr(_Sender, "send", _spy_send)

    svc = _service()
    _, token = _bound_elder_token(svc)
    asr = _BlockingAsr()
    client = _client(svc, asr=asr, admission=TurnAdmission(1, queue_timeout=5.0))
    with client.websocket_connect(f"/api/v1/ws/talk?token={token}") as ws:
        ws.send_bytes(b"audio-1")
        assert asr.entered.wait(5.0), "第一輪應該已經進到辨識裡、正持有名額"
        ws.send_bytes(b"audio-2")
        frame = _receive_frame(ws)
        assert frame["type"] == "queued"
        asr.release.set()

    queued_calls = [timeout for kind, timeout in calls if kind == "queued"]
    assert queued_calls, "應該至少送出一次 queued 訊框，才測得到它的逾時設定"
    assert all(timeout == 1.0 for timeout in queued_calls), (
        f"queued 訊框應使用短逾時（1 秒）避免拖住全域入場，而不是預設的 5 秒：{queued_calls}"
    )
