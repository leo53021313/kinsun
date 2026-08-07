"""LineApiMessenger：以假 SDK client 驗證各 API 的請求組裝（不打真 LINE）。

沿用 test_llm.py 的手法：真建構子（載入 SDK 的訊息模型），再把 ApiClient／
MessagingApi／MessagingApiBlob 換成替身；訊息模型（TextMessage 等）維持真品，
連請求形狀一起驗。
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from kinsun.channels.line.messenger import (
    LINE_API_TIMEOUT_SECONDS,
    LINE_SEND_MAX_ATTEMPTS,
    LineApiMessenger,
    LineOutboundChannel,
)


class _FakeApiClient:
    def __init__(self, configuration) -> None:
        self._configuration = configuration

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _messenger(*, profile_raises: bool = False) -> tuple[LineApiMessenger, list]:
    calls: list = []

    kwargs_seen: list[dict] = []

    class _FakeApi:
        def __init__(self, api_client) -> None:
            pass

        def reply_message(self, request, **kwargs) -> None:
            kwargs_seen.append(kwargs)
            calls.append(("reply", request))

        def push_message(self, request, **kwargs) -> None:
            kwargs_seen.append(kwargs)
            calls.append(("push", request))

        def get_profile(self, line_user_id: str, **kwargs):
            kwargs_seen.append(kwargs)
            if profile_raises:
                raise RuntimeError("api down")
            return SimpleNamespace(display_name="阿孫")

        def link_rich_menu_id_to_user(self, line_user_id: str, rich_menu_id: str, **kwargs) -> None:
            kwargs_seen.append(kwargs)
            calls.append(("link", line_user_id, rich_menu_id))

    class _FakeBlob:
        def __init__(self, api_client) -> None:
            pass

        def get_message_content(self, message_id: str, **kwargs) -> bytes:
            kwargs_seen.append(kwargs)
            calls.append(("blob", message_id))
            return b"AUDIO"

    messenger = LineApiMessenger("dummy-token")
    messenger._ApiClient = _FakeApiClient
    messenger._MessagingApi = _FakeApi
    messenger._MessagingApiBlob = _FakeBlob
    messenger.kwargs_seen = kwargs_seen  # 測試用：驗證每個出口都帶了逾時
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


# ── 逾時：每一個出口都必須帶（2026-07-27）──
#
# LINE API 一旦假死，該輪對話永遠不返回，佔住一個 uvicorn worker 與一條 Postgres 連線；
# 家屬危急通報又排在回覆生成之前（pipeline.py），卡住的代價是長輩連回覆都拿不到。
# 本專案為完全同型的問題付過兩次學費：llm.py:152-162（Gemini 的 timeout 存進欄位卻從沒
# 傳給 SDK）與 db.py 的 TCP keepalive 設定（見 db.py「連線層存活設定」區塊，防的是
# 「對端連線真的消失、作業系統不通知」這類真實故障；⚠️ 不是 2026-07-26 排程器靜默
# 停擺七小時的根因——那次根因是 try_claim 浮點等值比對，見 docs/dev/14 v1.17）。


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("reply_text", ("rt-1", "早安")),
        ("push_text", ("U-1", "記得吃藥")),
        ("get_audio", ("mid-1",)),
        ("display_name", ("U-1",)),
        ("link_rich_menu", ("U-1", "menu-1")),
        ("reply_voice", ("rt-1", "https://x/a.m4a", 800, "好喔")),
    ],
)
def test_every_line_api_call_carries_a_timeout(method, args):
    """逐一列出所有出口——新增方法時漏傳逾時，這條會紅。"""
    messenger, _ = _messenger()
    getattr(messenger, method)(*args)
    assert messenger.kwargs_seen, f"{method} 沒有呼叫任何 LINE API"
    for kwargs in messenger.kwargs_seen:
        assert "_request_timeout" in kwargs, f"{method} 沒有傳 _request_timeout"
        assert kwargs["_request_timeout"] == LINE_API_TIMEOUT_SECONDS


def test_urllib3_retries_are_disabled_so_the_timeout_is_a_real_bound():
    """`_request_timeout` 是每次嘗試的上限，不是總時限。

    黑洞位址（192.0.2.1，RFC 5737 TEST-NET-1）實測：urllib3 預設 retries=None 會自己
    重試 3 次，逾時設 2 秒實際 8 秒才放棄，且全程無日誌。關掉之後 2 秒就是 2 秒。
    """
    messenger, _ = _messenger()
    assert messenger._configuration.retries == 0


def test_timeout_is_configurable_per_instance():
    messenger, _ = _messenger()
    messenger._timeout = 3.0
    messenger.push_text("U-1", "記得吃藥")
    assert messenger.kwargs_seen[0]["_request_timeout"] == 3.0


def test_outbound_channel_delegates_to_push():
    messenger, calls = _messenger()
    LineOutboundChannel(messenger).send_text("U-1", "提醒")
    kind, request = calls[0]
    assert kind == "push"
    assert request.to == "U-1"


# ── 出站重試：只補「確定沒送出去」的那幾種（2026-07-27）──
#
# urllib3 的隱形重試已關掉（見上），所以一次網路抖動就等於一則危急通知永久消失。
# 重試改在這一層做——看得見、有日誌、且能挑對象。挑對象是重點：家屬收到兩則一模一樣
# 的危急警報，比漏收一則更容易讓人以後不再相信這個警報。


class _FlakyMessenger:
    """依序拋出腳本裡的例外；None 代表這次成功。"""

    def __init__(self, script) -> None:
        self.script = list(script)
        self.attempts = 0

    def push_text(self, line_user_id: str, text: str) -> None:
        self.attempts += 1
        exc = self.script.pop(0) if self.script else None
        if exc is not None:
            raise exc


def _channel(script, slept=None):
    messenger = _FlakyMessenger(script)
    channel = LineOutboundChannel(messenger, sleep=(slept.append if slept is not None else None))
    return channel, messenger


def _max_retry_error():
    from urllib3.exceptions import MaxRetryError

    return MaxRetryError(pool=None, url="https://api.line.me", reason=OSError("connection refused"))


def _service_exception():
    from linebot.v3.messaging.exceptions import ServiceException

    return ServiceException(status=503, reason="Service Unavailable")


def test_connection_failure_is_retried_until_it_succeeds():
    """連線根本沒建立起來＝請求沒送出去，重試不可能造成重複投遞。"""
    slept: list[float] = []
    channel, messenger = _channel([_max_retry_error(), None], slept)
    channel.send_text("U-1", "危急通知")
    assert messenger.attempts == 2
    assert slept, "重試之間必須退避，不可連打"


def test_server_error_is_retried():
    """5xx＝LINE 自己沒處理成功，重送是安全的。"""
    slept: list[float] = []
    channel, messenger = _channel([_service_exception(), None], slept)
    channel.send_text("U-1", "危急通知")
    assert messenger.attempts == 2


def test_read_timeout_is_never_retried():
    """⚠️ 這是本次最重要的一條：逾時代表 LINE 收到了但沒回應，那則通知可能已經送達。

    重試會讓家屬收到兩則一模一樣的危急警報。寧可記一次失敗，也不要製造重複警報。
    """
    from urllib3.exceptions import ReadTimeoutError

    channel, messenger = _channel([ReadTimeoutError(pool=None, url="x", message="timed out")])
    with pytest.raises(ReadTimeoutError):
        channel.send_text("U-1", "危急通知")
    assert messenger.attempts == 1


def test_client_errors_are_never_retried():
    """4xx＝請求本身有問題（token 失效、對象封鎖），重送幾次都一樣，只是拖慢通報。"""
    from linebot.v3.messaging.exceptions import ForbiddenException

    channel, messenger = _channel([ForbiddenException(status=403, reason="blocked")])
    with pytest.raises(ForbiddenException):
        channel.send_text("U-1", "危急通知")
    assert messenger.attempts == 1


def test_retries_are_bounded_and_the_error_still_surfaces():
    """重試用盡仍要把例外往上拋——ChannelRouter 據此記成投遞失敗，語意不可被吞掉。"""
    slept: list[float] = []
    channel, messenger = _channel([_max_retry_error()] * 10, slept)
    with pytest.raises(Exception):  # noqa: B017 - 型別不重要，重點是有拋出來
        channel.send_text("U-1", "危急通知")
    assert messenger.attempts == LINE_SEND_MAX_ATTEMPTS


def test_retry_is_logged(caplog):
    """urllib3 的隱形重試查不到，這一層的必須查得到。"""
    channel, _ = _channel([_max_retry_error(), None], [])
    with caplog.at_level(logging.WARNING, logger="kinsun.channels.line"):
        channel.send_text("U-1", "危急通知")
    assert any("重試" in r.message for r in caplog.records)
