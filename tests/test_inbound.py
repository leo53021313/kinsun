from types import SimpleNamespace

from kinsun.channels.inbound import (
    BIND_FIRST_PROMPT,
    FALLBACK_PROMPT,
    NON_AUDIO_PROMPT,
    InboundMessage,
    dispatch,
)
from kinsun.speech.asr import ASRError


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

    def process(self, audio, *, session_id):
        self.calls.append((audio, session_id))
        if self._boom is not None:
            raise self._boom
        return SimpleNamespace(text=self._text)


class _Binding:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def handle(self, session_id, text):
        self.calls.append((session_id, text))
        return self._reply


class _Gate:
    def __init__(self, allow):
        self._allow = allow

    def allows(self, session_id):
        return self._allow


def _msg(kind, *, reply, text="", audio=b"", session_id="U-1"):
    return InboundMessage(session_id, kind, text, audio, reply)


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
    assert pipe.calls == [(b"xy", "U-1")]
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
