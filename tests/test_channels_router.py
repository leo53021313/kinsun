"""ChannelRouter 出站路由測試：fan-out、單通道失敗隔離、無綁定情形。"""

from kinsun.accounts.models import Channel, ChannelBinding, PrincipalType
from kinsun.channels.outbound import FakeOutboundChannel
from kinsun.channels.router import ChannelRouter
from kinsun.notifications.models import NotificationSeverity


class _Directory:
    def __init__(self, bindings):
        self._bindings = bindings

    def list_channel_bindings_for_principal(self, principal_type, principal_id):
        return [
            b
            for b in self._bindings
            if b.principal_type == principal_type and b.principal_id == principal_id
        ]


def _binding(channel, external_id, principal_id="e1"):
    return ChannelBinding(channel, external_id, PrincipalType.ELDER, principal_id, 1000.0)


def test_sends_to_all_bound_channels():
    line = FakeOutboundChannel()
    app = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.LINE, "U-1"), _binding(Channel.APP, "dev-1")]),
        {Channel.LINE: line, Channel.APP: app},
    )
    sent = router.send_text(PrincipalType.ELDER, "e1", "哈囉")
    assert sent == 2
    assert line.sent == [("U-1", "哈囉")]
    assert app.sent == [("dev-1", "哈囉")]


def test_skips_channels_without_adapter():
    line = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.LINE, "U-1"), _binding(Channel.APP, "dev-1")]),
        {Channel.LINE: line},  # App 通道尚未接上 adapter
    )
    assert router.send_text(PrincipalType.ELDER, "e1", "哈囉") == 1
    assert line.sent == [("U-1", "哈囉")]


def test_no_bindings_sends_nothing():
    line = FakeOutboundChannel()
    router = ChannelRouter(_Directory([]), {Channel.LINE: line})
    assert router.send_text(PrincipalType.ELDER, "e1", "哈囉") == 0
    assert line.sent == []
    assert router.has_route(PrincipalType.ELDER, "e1") is False


def test_has_route_true_only_with_adapter():
    router = ChannelRouter(
        _Directory([_binding(Channel.APP, "dev-1")]),
        {Channel.LINE: FakeOutboundChannel()},  # 綁了 App 但沒有 App adapter
    )
    assert router.has_route(PrincipalType.ELDER, "e1") is False


def test_send_text_channels_returns_succeeded_channel_names():
    """✅ 庚-16（A-41）：回傳實際成功的通道名，供送達留痕標註語意。"""
    line = FakeOutboundChannel()
    app = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.LINE, "U-1"), _binding(Channel.APP, "dev-1")]),
        {Channel.LINE: line, Channel.APP: app},
    )
    assert router.send_text_channels(PrincipalType.ELDER, "e1", "哈囉") == ["line", "app"]


class _BoomChannel:
    # ⚠️ 簽章必須跟著 OutboundChannel 走（含 severity）：ChannelRouter 的
    # `except Exception` 連 TypeError 都吞，簽章不合會讓這支替身「因為參數對不上」
    # 而失敗，測試照樣綠——但驗到的就不再是「通道自己壞掉時其他通道不受影響」
    # 這件事了（2026-08-01 加 severity 時實測踩到，非推測）。
    def send_text(self, external_id, text, *, severity=NotificationSeverity.NOTICE):
        raise RuntimeError("channel down")


def test_single_channel_failure_isolated():
    line = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.APP, "dev-1"), _binding(Channel.LINE, "U-1")]),
        {Channel.LINE: line, Channel.APP: _BoomChannel()},
    )
    assert router.send_text(PrincipalType.ELDER, "e1", "哈囉") == 1
    assert line.sent == [("U-1", "哈囉")]


def test_send_text_defaults_to_notice():
    """不指定＝一般通知。預設若是 alert，每一則用藥提醒都會變成紅色警報。"""
    app = FakeOutboundChannel()
    router = ChannelRouter(_Directory([_binding(Channel.APP, "dev-1")]), {Channel.APP: app})
    router.send_text(PrincipalType.ELDER, "e1", "早上該吃藥囉")
    assert app.sent_severities == [NotificationSeverity.NOTICE]


def test_send_text_channels_forwards_severity_to_every_channel():
    """severity 原樣轉交每一個可達通道，路由層不解讀也不改寫。

    ⚠️ 兩個通道都要驗：路由是 fan-out，只把 severity 傳給第一個通道的寫法
    （或只傳給 App 通道的「聰明」寫法）在單通道測試下看不出來。
    """
    line = FakeOutboundChannel()
    app = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.LINE, "U-1"), _binding(Channel.APP, "dev-1")]),
        {Channel.LINE: line, Channel.APP: app},
    )
    # `_binding` 一律建 ELDER 綁定，principal_type 必須對上才路由得到。
    router.send_text_channels(
        PrincipalType.ELDER, "e1", "跌倒了", severity=NotificationSeverity.ALERT
    )
    assert line.sent_severities == [NotificationSeverity.ALERT]
    assert app.sent_severities == [NotificationSeverity.ALERT]


def test_send_text_counts_channels_and_still_forwards_severity():
    """`send_text`（回通道數的那支）也要轉交 severity——它是 safety 以外呼叫端走的路。

    ⚠️ 它是 `send_text_channels` 的薄包裝，很容易在包裝時漏掉 keyword 轉交，
    而回傳的通道數完全看不出這件事。
    """
    app = FakeOutboundChannel()
    router = ChannelRouter(_Directory([_binding(Channel.APP, "dev-1")]), {Channel.APP: app})
    assert (
        router.send_text(PrincipalType.ELDER, "e1", "跌倒了", severity=NotificationSeverity.ALERT)
        == 1
    )
    assert app.sent_severities == [NotificationSeverity.ALERT]
