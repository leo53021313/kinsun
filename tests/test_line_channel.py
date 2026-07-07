from types import SimpleNamespace

from kinsun.accounts.models import Channel
from kinsun.channels.line.channel import LineChannel
from tests.fakes import FakeTraceStore


class _Messenger:
    def __init__(self):
        self.replied = []
        self.audio_calls = []
        self.voice = []

    def get_audio(self, message_id):
        self.audio_calls.append(message_id)
        return b"\x00\x01"

    def reply_text(self, reply_token, text):
        self.replied.append((reply_token, text))

    def reply_voice(self, reply_token, audio_url, duration_ms, text):
        self.voice.append((reply_token, audio_url, duration_ms, text))


def _audio_event(uid="U-1"):
    return SimpleNamespace(
        reply_token="rt-1",
        message=SimpleNamespace(type="audio", id="m-1"),
        source=SimpleNamespace(user_id=uid),
    )


def _text_event():
    return SimpleNamespace(
        reply_token="rt-2",
        message=SimpleNamespace(type="text", id="m-2", text="設定"),
        source=SimpleNamespace(user_id="U-2"),
    )


def _sticker_event():
    return SimpleNamespace(
        reply_token="rt-3",
        message=SimpleNamespace(type="sticker", id="m-3"),
        source=SimpleNamespace(user_id="U-3"),
    )


def test_text_event_normalized():
    msg = LineChannel(_Messenger()).inbound(_text_event())
    assert msg.kind == "text"
    assert msg.text == "設定"
    assert msg.channel == Channel.LINE
    assert msg.external_id == "U-2"
    assert msg.audio == b""


def test_audio_event_fetches_bytes():
    m = _Messenger()
    msg = LineChannel(m).inbound(_audio_event())
    assert msg.kind == "audio"
    assert msg.audio == b"\x00\x01"
    assert m.audio_calls == ["m-1"]


def test_sticker_is_other():
    assert LineChannel(_Messenger()).inbound(_sticker_event()).kind == "other"


def test_missing_token_returns_none():
    ev = SimpleNamespace(
        reply_token=None,
        message=SimpleNamespace(type="text", text="x"),
        source=SimpleNamespace(user_id="U"),
    )
    assert LineChannel(_Messenger()).inbound(ev) is None


def test_missing_user_id_is_unknown():
    assert LineChannel(_Messenger()).inbound(_audio_event(uid=None)).external_id == "unknown"


def test_reply_binds_to_messenger():
    m = _Messenger()
    msg = LineChannel(m).inbound(_text_event())
    msg.reply("哈囉")
    assert m.replied == [("rt-2", "哈囉")]


def test_inbound_binds_reply_voice_to_reply_token():
    messenger = _Messenger()
    msg = LineChannel(messenger).inbound(_audio_event())
    msg.reply_voice("http://x/a.m4a", 500, "文字")
    assert messenger.voice == [("rt-1", "http://x/a.m4a", 500, "文字")]


class _StubAudioPublisher:
    def __init__(self, url="https://x/in.m4a", fail=False):
        self.url = url
        self.fail = fail

    def publish(self, audio, *, content_type):
        if self.fail:
            raise RuntimeError("上傳失敗")
        return self.url


def test_audio_inbound_records_webhook_event_and_uploads():
    traces = FakeTraceStore()
    channel = LineChannel(
        _Messenger(),
        traces=traces,
        inbound_audio=_StubAudioPublisher(),
        new_id=lambda: "trace-1",
    )
    msg = channel.inbound(_audio_event())
    assert msg.trace_id == "trace-1"
    assert msg.audio_url == "https://x/in.m4a"
    assert len(traces.webhook_events) == 1
    assert traces.webhook_events[0].trace_id == "trace-1"
    assert traces.webhook_events[0].line_user_id == "U-1"
    assert traces.webhook_events[0].message_type == "audio"


def test_audio_upload_failure_leaves_url_empty():
    channel = LineChannel(
        _Messenger(),
        traces=FakeTraceStore(),
        inbound_audio=_StubAudioPublisher(fail=True),
        new_id=lambda: "trace-1",
    )
    # 上傳失敗不中斷對話，URL 留空
    assert channel.inbound(_audio_event()).audio_url == ""


def test_text_inbound_records_webhook_event():
    traces = FakeTraceStore()
    channel = LineChannel(_Messenger(), traces=traces, new_id=lambda: "trace-2")
    msg = channel.inbound(_text_event())
    assert msg.trace_id == "trace-2"
    assert traces.webhook_events[0].message_type == "text"


def test_channel_without_traces_keeps_working():
    msg = LineChannel(_Messenger()).inbound(_text_event())
    assert msg is not None
    assert msg.trace_id != ""  # 仍會產生 trace_id 供管線使用
