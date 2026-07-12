"""App 出站 adapter（✅ D-12，甲-6）：send_text ＝落一筆 App 內通知。"""

from kinsun.channels.app.outbound import AppOutboundChannel
from kinsun.notifications.store import FakeAppNotificationStore


def test_send_text_persists_notification():
    store = FakeAppNotificationStore()
    AppOutboundChannel(store).send_text("ext-1", "阿蘭提到跌倒，請留意")
    assert [(n.external_id, n.content) for n in store.recorded] == [
        ("ext-1", "阿蘭提到跌倒，請留意")
    ]
