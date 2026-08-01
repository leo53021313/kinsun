"""App 出站 adapter（✅ D-12，甲-6）：send_text ＝落一筆 App 內通知。"""

from kinsun.channels.app.outbound import AppOutboundChannel
from kinsun.notifications.models import NotificationSeverity
from kinsun.notifications.store import FakeAppNotificationStore


def test_send_text_persists_notification():
    store = FakeAppNotificationStore()
    AppOutboundChannel(store).send_text("ext-1", "阿蘭提到跌倒，請留意")
    assert [(n.external_id, n.content) for n in store.recorded] == [
        ("ext-1", "阿蘭提到跌倒，請留意")
    ]


def test_send_text_defaults_to_notice():
    """不指定＝一般通知：用藥提醒與主動關懷全部走這條。"""
    store = FakeAppNotificationStore()
    AppOutboundChannel(store).send_text("ext-1", "阿嬤，早上該吃藥囉")
    assert store.recorded[0].severity == NotificationSeverity.NOTICE


def test_send_text_passes_alert_severity_through_to_the_store():
    """危急警報的分級必須真的落到庫裡——這是「畫面上分得出來」的唯一資料來源。

    ⚠️ 這條守的是 adapter 這一節：`ChannelRouter` 把 severity 交到這裡之後，
    只要少寫一個 `severity=`，整條線就會在最後一公尺無聲降級成一般通知，
    而上下游的測試全都還是綠的。
    """
    store = FakeAppNotificationStore()
    AppOutboundChannel(store).send_text(
        "ext-1", "王阿嬤剛剛說：「我跌倒了」", severity=NotificationSeverity.ALERT
    )
    assert store.recorded[0].severity == NotificationSeverity.ALERT
