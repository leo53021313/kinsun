from types import SimpleNamespace

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

    def process(self, audio, *, elder_id, line_user_id="", trace_id="", audio_url=""):
        self.calls.append((audio, elder_id))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)

    def process_text(self, text, *, elder_id, line_user_id="", trace_id=""):
        self.text_calls.append((text, elder_id))
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

    def resolve_elder(self, line_user_id):
        return "e-1" if self._allow else None


class _VoicePipeline:
    def __init__(self, result):
        self._result = result

    def process(self, audio, *, elder_id, line_user_id="", trace_id="", audio_url=""):
        return self._result


class _SpyVoice:
    def __init__(self):
        self.delivered = []

    def deliver(self, msg, result):
        self.delivered.append((msg.line_user_id, result.text))


def _msg(kind, *, reply, text="", audio=b"", line_user_id="U-1"):
    return InboundMessage(line_user_id, kind, text, audio, reply)


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


def test_text_none_falls_back_to_prompt():
    r = _Replies()
    dispatch(
        _msg("text", text="閒聊", reply=r),
        pipeline=_Pipeline(),
        binding=_Binding(None),
        gate=_Gate(True),
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
    return InboundMessage("U-1", "audio", "", b"x", cap.reply, cap.reply_voice)


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
    msg = InboundMessage("U-1", "audio", "", b"xy", r, trace_id="t2")
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
