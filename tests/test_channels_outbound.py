"""OutboundChannel 門面與 LINE adapter 的離線測試。"""

from kinsun.channels.line.messenger import LineOutboundChannel
from kinsun.channels.outbound import FakeOutboundChannel


class _SpyMessenger:
    def __init__(self):
        self.pushed = []

    def push_text(self, line_user_id, text):
        self.pushed.append((line_user_id, text))


def test_fake_records_sends_in_order():
    ch = FakeOutboundChannel()
    ch.send_text("U-1", "早安")
    ch.send_text("U-2", "吃藥囉")
    assert ch.sent == [("U-1", "早安"), ("U-2", "吃藥囉")]


def test_line_adapter_delegates_to_push_text():
    messenger = _SpyMessenger()
    LineOutboundChannel(messenger).send_text("U-9", "回診提醒")
    assert messenger.pushed == [("U-9", "回診提醒")]
