"""ChannelRouter 出站路由測試：fan-out、單通道失敗隔離、無綁定情形。"""

from kinsun.accounts.models import Channel, ChannelBinding, PrincipalType
from kinsun.channels.outbound import FakeOutboundChannel
from kinsun.channels.router import ChannelRouter


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
    def send_text(self, external_id, text):
        raise RuntimeError("channel down")


def test_single_channel_failure_isolated():
    line = FakeOutboundChannel()
    router = ChannelRouter(
        _Directory([_binding(Channel.APP, "dev-1"), _binding(Channel.LINE, "U-1")]),
        {Channel.LINE: line, Channel.APP: _BoomChannel()},
    )
    assert router.send_text(PrincipalType.ELDER, "e1", "哈囉") == 1
    assert line.sent == [("U-1", "哈囉")]
