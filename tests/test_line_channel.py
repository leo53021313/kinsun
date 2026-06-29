from types import SimpleNamespace

from kinsun.channels.line.channel import LineChannel


class _Messenger:
    def __init__(self):
        self.replied = []
        self.audio_calls = []

    def get_audio(self, message_id):
        self.audio_calls.append(message_id)
        return b"\x00\x01"

    def reply_text(self, reply_token, text):
        self.replied.append((reply_token, text))


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
    assert msg.session_id == "U-2"
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
    assert LineChannel(_Messenger()).inbound(_audio_event(uid=None)).session_id == "unknown"


def test_reply_binds_to_messenger():
    m = _Messenger()
    msg = LineChannel(m).inbound(_text_event())
    msg.reply("哈囉")
    assert m.replied == [("rt-2", "哈囉")]
