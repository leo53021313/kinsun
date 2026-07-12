"""LineApiMessenger：以假 SDK client 驗證各 API 的請求組裝（不打真 LINE）。

沿用 test_llm.py 的手法：真建構子（載入 SDK 的訊息模型），再把 ApiClient／
MessagingApi／MessagingApiBlob 換成替身；訊息模型（TextMessage 等）維持真品，
連請求形狀一起驗。
"""

from __future__ import annotations

from types import SimpleNamespace

from kinsun.channels.line.messenger import LineApiMessenger, LineOutboundChannel


class _FakeApiClient:
    def __init__(self, configuration) -> None:
        self._configuration = configuration

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _messenger(*, profile_raises: bool = False) -> tuple[LineApiMessenger, list]:
    calls: list = []

    class _FakeApi:
        def __init__(self, api_client) -> None:
            pass

        def reply_message(self, request) -> None:
            calls.append(("reply", request))

        def push_message(self, request) -> None:
            calls.append(("push", request))

        def get_profile(self, line_user_id: str):
            if profile_raises:
                raise RuntimeError("api down")
            return SimpleNamespace(display_name="阿孫")

        def link_rich_menu_id_to_user(self, line_user_id: str, rich_menu_id: str) -> None:
            calls.append(("link", line_user_id, rich_menu_id))

    class _FakeBlob:
        def __init__(self, api_client) -> None:
            pass

        def get_message_content(self, message_id: str) -> bytes:
            calls.append(("blob", message_id))
            return b"AUDIO"

    messenger = LineApiMessenger("dummy-token")
    messenger._ApiClient = _FakeApiClient
    messenger._MessagingApi = _FakeApi
    messenger._MessagingApiBlob = _FakeBlob
    return messenger, calls


def test_reply_text_builds_text_message():
    messenger, calls = _messenger()
    messenger.reply_text("rt-1", "早安")
    kind, request = calls[0]
    assert kind == "reply"
    assert request.reply_token == "rt-1"
    assert request.messages[0].text == "早安"


def test_push_text_targets_line_user():
    messenger, calls = _messenger()
    messenger.push_text("U-1", "記得吃藥")
    kind, request = calls[0]
    assert kind == "push"
    assert request.to == "U-1"
    assert request.messages[0].text == "記得吃藥"


def test_reply_voice_with_text_appends_bubble():
    messenger, calls = _messenger()
    messenger.reply_voice("rt-1", "https://x/a.m4a", 800, "好喔")
    _, request = calls[0]
    assert request.messages[0].original_content_url == "https://x/a.m4a"
    assert request.messages[0].duration == 800
    assert request.messages[1].text == "好喔"


def test_reply_voice_without_text_sends_audio_only():
    messenger, calls = _messenger()
    messenger.reply_voice("rt-1", "https://x/a.m4a", 800, None)
    _, request = calls[0]
    assert len(request.messages) == 1


def test_get_audio_downloads_blob():
    messenger, calls = _messenger()
    assert messenger.get_audio("mid-1") == b"AUDIO"
    assert calls == [("blob", "mid-1")]


def test_display_name_returns_profile_name():
    messenger, _ = _messenger()
    assert messenger.display_name("U-1") == "阿孫"


def test_display_name_swallows_api_error():
    messenger, _ = _messenger(profile_raises=True)
    assert messenger.display_name("U-1") == ""


def test_link_rich_menu_passes_ids():
    messenger, calls = _messenger()
    messenger.link_rich_menu("U-1", "menu-1")
    assert calls == [("link", "U-1", "menu-1")]


def test_outbound_channel_delegates_to_push():
    messenger, calls = _messenger()
    LineOutboundChannel(messenger).send_text("U-1", "提醒")
    kind, request = calls[0]
    assert kind == "push"
    assert request.to == "U-1"
