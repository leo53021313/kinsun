from types import SimpleNamespace

from kinsun.accounts.models import Channel
from kinsun.channels.inbound import (
    BIND_FIRST_PROMPT,
    FALLBACK_PROMPT,
    NON_AUDIO_PROMPT,
    InboundMessage,
    VoiceReplyDelivery,
    dispatch,
)
from kinsun.llm import LLMError
from kinsun.speech.asr import ASRError
from kinsun.speech.tts import TtsResult
from tests.fakes import FakeTraceStore


class _Replies:
    def __init__(self):
        self.sent = []

    def __call__(self, text):
        self.sent.append(text)


class _Pipeline:
    def __init__(self, text="管線回覆", boom=None):
        self._text = text
        self._boom = boom
        self.calls = []
        self.text_calls = []
        self.obs_marks = []  # (external_id, channel) 觀測標記——庚-07 驗通道有貫穿

    def process(self, audio, *, elder_id, external_id="", channel="", trace_id="", audio_url=""):
        self.calls.append((audio, elder_id))
        self.obs_marks.append((external_id, channel))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)

    def process_text(self, text, *, elder_id, external_id="", channel="", trace_id=""):
        self.text_calls.append((text, elder_id))
        self.obs_marks.append((external_id, channel))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)


class _Binding:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def handle(self, line_user_id, text):
        self.calls.append((line_user_id, text))
        return self._reply


class _Gate:
    """resolve_elder 測試替身：allow=True 時把 line id 映到固定 elder id。"""

    def __init__(self, allow):
        self._allow = allow
        self.resolve_calls = 0

    def resolve_elder(self, channel, external_id):
        self.resolve_calls += 1
        return "e-1" if self._allow else None


class _VoicePipeline:
    def __init__(self, result):
        self._result = result

    def process(self, audio, *, elder_id, external_id="", channel="", trace_id="", audio_url=""):
        return self._result


class _SpyVoice:
    def __init__(self):
        self.delivered = []

    def deliver(self, msg, result):
        self.delivered.append((msg.external_id, result.text))


def _msg(kind, *, reply, text="", audio=b"", external_id="U-1"):
    return InboundMessage(Channel.LINE, external_id, kind, text, audio, reply)


def test_text_routes_to_binding():
    r = _Replies()
    binding = _Binding("已建立")
    dispatch(
        _msg("text", text="設定", reply=r),
        pipeline=_Pipeline(),
        binding=binding,
        gate=_Gate(True),
    )
    assert binding.calls == [("U-1", "設定")]
    assert r.sent == ["已建立"]


def test_text_default_runs_pipeline():
    """✅ D-11（甲-4）：文字輸入預設走完整對話管線。"""
    r = _Replies()
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("text", text="閒聊", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.text_calls == [("閒聊", "e-1")]
    assert r.sent == ["回覆"]


def test_pipeline_receives_external_id_and_channel_for_observability():
    """✅ 庚-07（A-8）：來源通道與外部識別碼一路帶進管線供觀測五表標記。"""
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("text", text="閒聊", reply=_Replies(), external_id="U-9"),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.obs_marks == [("U-9", "line")]  # channel 取自 InboundMessage.channel


def test_dispatch_skips_resolve_when_elder_id_provided():
    """✅ 庚-12（A-11）：呼叫端（App turns）已解析過本人時傳入 elder_id，
    dispatch 不再重查閘門——省掉每輪一趟重複 DB 往返。"""
    gate = _Gate(True)
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("audio", audio=b"\x01", reply=_Replies()),
        pipeline=pipe,
        binding=_Binding(None),
        gate=gate,
        elder_id="e-pre",
    )
    assert gate.resolve_calls == 0
    assert pipe.calls == [(b"\x01", "e-pre")]


def test_dispatch_resolves_when_elder_id_not_provided():
    gate = _Gate(True)
    pipe = _Pipeline(text="回覆")
    dispatch(
        _msg("audio", audio=b"\x01", reply=_Replies()),
        pipeline=pipe,
        binding=_Binding(None),
        gate=gate,
    )
    assert gate.resolve_calls == 1
    assert pipe.calls == [(b"\x01", "e-1")]


def test_text_flag_off_falls_back_to_prompt():
    """關閉旗標＝維運逃生口：回到只收語音的提示。"""
    r = _Replies()
    dispatch(
        _msg("text", text="閒聊", reply=r),
        pipeline=_Pipeline(),
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=False,
    )
    assert r.sent == [NON_AUDIO_PROMPT]


def test_other_kind_replies_prompt():
    r = _Replies()
    dispatch(_msg("other", reply=r), pipeline=_Pipeline(), binding=_Binding(None), gate=_Gate(True))
    assert r.sent == [NON_AUDIO_PROMPT]


def test_text_flag_on_runs_pipeline():
    r = _Replies()
    pipe = _Pipeline(text="你說的是：哈囉")
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert pipe.text_calls == [("哈囉", "e-1")]
    assert r.sent == ["你說的是：哈囉"]


def test_text_flag_on_binding_command_still_routes_to_binding():
    r = _Replies()
    binding = _Binding("已建立")
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="設定", reply=r),
        pipeline=pipe,
        binding=binding,
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert binding.calls == [("U-1", "設定")]
    assert r.sent == ["已建立"]
    assert pipe.text_calls == []


def test_text_flag_on_blocked_when_gate_denies():
    r = _Replies()
    pipe = _Pipeline()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(False),
        text_input_enabled=True,
    )
    assert r.sent == [BIND_FIRST_PROMPT]
    assert pipe.text_calls == []


def test_text_flag_on_pipeline_error_replies_fallback():
    r = _Replies()
    dispatch(
        _msg("text", text="哈囉", reply=r),
        pipeline=_Pipeline(boom=LLMError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
        text_input_enabled=True,
    )
    assert r.sent == [FALLBACK_PROMPT]


def test_audio_blocked_when_gate_denies():
    r = _Replies()
    pipe = _Pipeline()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(False),
    )
    assert r.sent == [BIND_FIRST_PROMPT]
    assert pipe.calls == []


def test_audio_runs_pipeline_when_allowed():
    r = _Replies()
    pipe = _Pipeline(text="你說的是：早安")
    dispatch(
        _msg("audio", audio=b"xy", reply=r),
        pipeline=pipe,
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert pipe.calls == [(b"xy", "e-1")]
    assert r.sent == ["你說的是：早安"]


def test_audio_pipeline_error_replies_fallback():
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_Pipeline(boom=ASRError("boom")),
        binding=_Binding(None),
        gate=_Gate(True),
    )
    assert r.sent == [FALLBACK_PROMPT]


class _VoiceCapture:
    def __init__(self):
        self.text_sent = []
        self.voice_sent = []

    def reply(self, text):
        self.text_sent.append(text)

    def reply_voice(self, url, duration_ms, text):
        self.voice_sent.append((url, duration_ms, text))


class _Publisher:
    def __init__(self, url="http://x/a.m4a", boom=False):
        self._url = url
        self._boom = boom

    def publish(self, audio, *, content_type):
        if self._boom:
            from kinsun.audio.publisher import AudioPublishError

            raise AudioPublishError("boom")
        return self._url


def _voice_msg(cap):
    return InboundMessage(Channel.LINE, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice)


def test_deliver_text_when_no_audio():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="純文字", audio=None)
    )
    assert cap.text_sent == ["純文字"]
    assert cap.voice_sent == []


def test_deliver_voice_with_text():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="嗨", audio=b"A", duration_ms=800)
    )
    assert cap.voice_sent == [("http://x/a.m4a", 800, "嗨")]
    assert cap.text_sent == []


def test_deliver_voice_without_text_when_disabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=False).deliver(
        _voice_msg(cap), TtsResult(text="嗨", audio=b"A", duration_ms=800)
    )
    assert cap.voice_sent == [("http://x/a.m4a", 800, None)]


def test_deliver_falls_back_to_text_on_publish_error():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(boom=True), include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="退化文字", audio=b"A", duration_ms=800)
    )
    assert cap.text_sent == ["退化文字"]
    assert cap.voice_sent == []


def test_deliver_text_when_publisher_none():
    cap = _VoiceCapture()
    VoiceReplyDelivery(None, include_text=True).deliver(
        _voice_msg(cap), TtsResult(text="泡泡", audio=None)
    )
    assert cap.text_sent == ["泡泡"]


def test_audio_success_routes_to_voice_when_present():
    voice = _SpyVoice()
    dispatch(
        _msg("audio", audio=b"x", reply=_Replies()),
        pipeline=_VoicePipeline(TtsResult(text="語音回覆", audio=b"A", duration_ms=100)),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=voice,
    )
    assert voice.delivered == [("U-1", "語音回覆")]


def test_deliver_shows_transcript_when_enabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=True).deliver(
        _voice_msg(cap),
        TtsResult(text="好喔", audio=b"A", duration_ms=100, transcript="今天天氣真好"),
    )
    assert cap.voice_sent == [("http://x/a.m4a", 100, "辨識：今天天氣真好\n\n回復：好喔")]


def test_deliver_no_transcript_when_disabled():
    cap = _VoiceCapture()
    VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=False).deliver(
        _voice_msg(cap),
        TtsResult(text="好喔", audio=b"A", duration_ms=100, transcript="今天天氣真好"),
    )
    assert cap.voice_sent == [("http://x/a.m4a", 100, "好喔")]


def test_dispatch_records_voice_reply():
    traces = FakeTraceStore()
    cap = _VoiceCapture()
    msg = InboundMessage(
        Channel.LINE,
        "U-1",
        "audio",
        "",
        b"xy",
        cap.reply,
        cap.reply_voice,
        trace_id="t1",
        audio_url="https://x/in.m4a",
    )
    result = TtsResult(text="回覆", audio=b"\x00", duration_ms=800)
    voice = VoiceReplyDelivery(_Publisher(url="https://x/out.m4a"), include_text=True)
    dispatch(
        msg,
        pipeline=_VoicePipeline(result),
        binding=_Binding(None),
        gate=_Gate(True),
        voice=voice,
        traces=traces,
        timer=iter([0.0, 0.2]).__next__,
    )
    assert len(traces.replies) == 1
    assert traces.replies[0].trace_id == "t1"
    assert traces.replies[0].kind == "voice"
    assert traces.replies[0].audio_url == "https://x/out.m4a"
    assert traces.replies[0].latency_ms == 200


def test_dispatch_records_text_reply_when_no_voice():
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t2")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="純文字")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].kind == "text"
    assert traces.replies[0].audio_url == ""


def test_dispatch_stores_opik_trace_id_on_reply(monkeypatch):
    """care_conversation trace context 內抓到的 Opik trace id 隨 reply 落庫（供後台深連結）。"""
    from kinsun import tracing

    monkeypatch.setattr(tracing, "current_opik_trace_id", lambda: "opik-999")
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t9")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="嗨")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].opik_trace_id == "opik-999"


def test_dispatch_without_trace_id_records_nothing():
    traces = FakeTraceStore()
    r = _Replies()
    dispatch(
        _msg("audio", audio=b"x", reply=r),
        pipeline=_VoicePipeline(TtsResult(text="hi")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
    )
    assert traces.replies == []  # 無 trace_id（非觀測路徑）不記


def test_dispatch_records_round_trip_from_received_at():
    """✅ D-05（戊-2）：received_at（通道收件時刻）→ 回覆送達的端到端往返延遲落庫。"""
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t3", received_at=0.5)
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([1.0, 1.25]).__next__,
    )
    assert traces.replies[0].latency_ms == 250  # 發送段：1.0 → 1.25
    assert traces.replies[0].round_trip_ms == 750  # 端到端：0.5 → 1.25


def test_dispatch_round_trip_null_when_received_at_unknown():
    traces = FakeTraceStore()
    r = _Replies()
    msg = InboundMessage(Channel.LINE, "U-1", "audio", "", b"xy", r, trace_id="t4")
    dispatch(
        msg,
        pipeline=_VoicePipeline(TtsResult(text="回覆")),
        binding=_Binding(None),
        gate=_Gate(True),
        traces=traces,
        timer=iter([0.0, 0.1]).__next__,
    )
    assert traces.replies[0].round_trip_ms is None


class _ChunkedPipeline:
    """回傳已分段結果的管線替身，用來驗 dispatch 交出去的 outcome。"""

    def __init__(self, reply: str, chunk_count: int, transcript: str = "") -> None:
        self._result = TtsResult(
            text=reply, audio=b"A", duration_ms=900, transcript=transcript, chunk_count=chunk_count
        )

    def process(self, audio, **kwargs):
        return self._result

    def process_text(self, text, **kwargs):
        return self._result


def test_dispatch_reports_chunk_count_and_digest_of_the_real_reply():
    """digest 必須由**真正的回覆文字**算出，不是投遞層的顯示字串。

    ⚠️ 這條是實機驗證踩出來的（2026-07-26）：`ASR_DEBUG_SHOW_TRANSCRIPT=true` 時，
    文字泡泡會變成「辨識：…\\n\\n回復：…」，而分段端點是從 `turns` 讀**純回覆**重新
    切句比對。兩邊來源不同，雜湊就永遠對不上——每一段都被判為過期、回 409，長輩只
    聽得到第一句。單元測試若只驗「有沒有 digest」不會發現，故這裡把來源釘死。
    """
    from kinsun.speech.chunking import reply_digest

    reply = "阿公今天早上好嗎。今天天氣不錯，要不要出去走走？"
    cap = _VoiceCapture()
    msg = InboundMessage(
        Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice, received_at=1.0
    )

    outcome = dispatch(
        msg,
        pipeline=_ChunkedPipeline(reply, chunk_count=2, transcript="醫生說我血壓有點高"),
        binding=_Binding(None),
        gate=None,
        voice=VoiceReplyDelivery(_Publisher(), include_text=True, show_transcript=True),
        elder_id="e1",
    )

    assert outcome.chunk_count == 2
    assert outcome.reply_digest == reply_digest(reply)
    # 顯示字串確實帶了 debug 前綴——證明本測試真的踩在那個分岔上。
    assert cap.voice_sent[0][2].startswith("辨識：")


def test_unchunked_reply_carries_no_digest():
    """沒分段就不該給 digest——前端據此判斷「不必再拉後續段落」。"""
    cap = _VoiceCapture()
    msg = InboundMessage(Channel.APP, "U-1", "audio", "", b"x", cap.reply, cap.reply_voice)

    outcome = dispatch(
        msg,
        pipeline=_ChunkedPipeline("就這一句話而已喔阿公", chunk_count=0),
        binding=_Binding(None),
        gate=None,
        voice=VoiceReplyDelivery(_Publisher(), include_text=True),
        elder_id="e1",
    )

    assert outcome.chunk_count == 0
    assert outcome.reply_digest == ""
