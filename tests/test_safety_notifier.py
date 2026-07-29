import logging

from kinsun.accounts.models import ElderGuardian, PrincipalType, Role
from kinsun.safety.deliveries import FakeRiskNotificationLogStore
from kinsun.safety.notifier import GuardianNotifier, LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify(
            "e-1", RiskAssessment(RiskTier.L2, 0.9, "求救", ["keyword:absolute"]), "救命"
        )
    assert any("L2" in r.message and "e-1" in r.message for r in caplog.records)
    # 原話與 reason 都是對話內容，不進 log（2026-07-27 政策）。
    assert all("救命" not in r.message for r in caplog.records)


class _SpyRouter:
    """ChannelRouter 替身：記錄 (principal_type, principal_id, text)。

    `fail_on`＝有綁通道但送出全數失敗；`no_route_on`＝根本沒綁任何通道。兩者在
    `send_text_channels` 的回傳上無法區分（都是空清單），這正是本模組要分流的東西。
    """

    def __init__(self, fail_on=None, channels=("line",), no_route_on=()):
        self.sent = []
        self._fail_on = fail_on
        self._channels = list(channels)
        self._no_route_on = set(no_route_on)

    def has_route(self, principal_type, principal_id):
        return principal_id not in self._no_route_on

    def send_text_channels(self, principal_type, principal_id, text):
        if principal_id == self._fail_on or principal_id in self._no_route_on:
            return []
        self.sent.append((principal_type, principal_id, text))
        return list(self._channels)


def _eg(guardian_id, order):
    return ElderGuardian("e-elder", guardian_id, Role.GUARDIAN, order)


class _StubDirectory:
    def __init__(self, guardian_ids, *, raises=False):
        self._guardian_ids = guardian_ids
        self._raises = raises

    def guardians_of(self, elder_id):
        if self._raises:
            raise RuntimeError("db down")
        return [_eg(g, i + 1) for i, g in enumerate(self._guardian_ids)]


def test_pushes_to_all_guardians_in_order():
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router)
    notifier.notify(
        "e-elder",
        RiskAssessment(RiskTier.L2, 0.8, "明確表示胸口不適", ["symptom"]),
        "我胸口悶悶的，整天都不舒服",
    )
    assert [(t, g) for t, g, _ in router.sent] == [
        (PrincipalType.GUARDIAN, "g1"),
        (PrincipalType.GUARDIAN, "g2"),
    ]
    assert "我胸口悶悶的，整天都不舒服" in router.sent[0][2]


def test_alert_quotes_the_elders_words_not_the_llm_reason():
    """文案只放長輩原話（2026-07-29 Leo 定案）：緊不緊急由家屬自行判斷，
    不轉述分級器的 reason，也不放家屬看不懂的「風險等級」字樣。"""
    router = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router).notify(
        "e-elder",
        RiskAssessment(RiskTier.L2, 0.9, "明確表示持續胸痛", ["llm"]),
        "我胸口好痛，喘不過氣",
    )
    text = router.sent[0][2]
    assert "我胸口好痛，喘不過氣" in text
    assert "明確表示持續胸痛" not in text
    assert "風險等級" not in text


def test_delivery_log_records_success_and_failure_per_guardian():
    """✅ D-36（丙-7）：每位家屬的送達與否獨立留痕——「當時有沒有收到」查得到。"""
    router = _SpyRouter(fail_on="g2")
    deliveries = FakeRiskNotificationLogStore()
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router, deliveries=deliveries)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]), "我胸口悶")
    assert [(d.guardian_id, d.delivered) for d in deliveries.recorded] == [
        ("g1", True),
        ("g2", False),
    ]
    assert deliveries.recorded[0].elder_id == "e-elder"
    assert deliveries.recorded[0].tier == RiskTier.L2


def test_delivery_log_records_channels():
    """✅ 庚-16（A-41）：留痕記實際走的通道——App 落庫≠真送達，語意由通道還原。"""
    router = _SpyRouter(channels=("app",))
    deliveries = FakeRiskNotificationLogStore()
    notifier = GuardianNotifier(_StubDirectory(["g1"]), router, deliveries=deliveries)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]), "我胸口悶")
    assert deliveries.recorded[0].channels == "app"

    router2 = _SpyRouter(channels=("line", "app"))
    deliveries2 = FakeRiskNotificationLogStore()
    GuardianNotifier(_StubDirectory(["g1"]), router2, deliveries=deliveries2).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []), "我胸口悶"
    )
    assert deliveries2.recorded[0].channels == "line,app"


# ── 未綁通道 vs 真的送失敗（2026-07-27）──
#
# 兩者先前都被記成 delivered=False，而 admin 的投遞失敗告警是全域
# `WHERE delivered = FALSE` —— 家屬還沒綁 LINE 這種常態情形會持續灌進告警，
# 把真正的送達失敗淹掉。分流之後告警只算真的失敗。


def test_unbound_guardian_is_recorded_as_no_route_not_failure():
    router = _SpyRouter(no_route_on={"g2"})
    deliveries = FakeRiskNotificationLogStore()
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router, deliveries=deliveries)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]), "我胸口悶")
    assert [(d.guardian_id, d.delivered, d.outcome) for d in deliveries.recorded] == [
        ("g1", True, "sent"),
        ("g2", False, "no_route"),
    ]


def test_send_failure_is_still_recorded_as_failed():
    router = _SpyRouter(fail_on="g1")
    deliveries = FakeRiskNotificationLogStore()
    notifier = GuardianNotifier(_StubDirectory(["g1"]), router, deliveries=deliveries)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []), "我胸口悶")
    assert deliveries.recorded[0].outcome == "failed"
    assert deliveries.recorded[0].delivered is False


def test_unbound_guardian_is_not_counted_by_the_failure_alert():
    """告警只算真的失敗——這是本次分流的目的。"""
    deliveries = FakeRiskNotificationLogStore(clock=lambda: 100.0)
    GuardianNotifier(
        _StubDirectory(["g1", "g2"]),
        _SpyRouter(fail_on="g1", no_route_on={"g2"}),
        deliveries=deliveries,
    ).notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []), "我胸口悶")
    assert len(deliveries.recorded) == 2  # 兩筆都有留痕（稽核不可少）
    assert deliveries.count_failed_since(0.0) == 1  # 但只有一筆算失敗


def test_unbound_guardian_is_not_sent_to():
    """沒有可達通道就不必白呼叫一次出站——但仍要留痕。"""
    router = _SpyRouter(no_route_on={"g1"})
    GuardianNotifier(_StubDirectory(["g1"]), router).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []), "我胸口悶"
    )
    assert router.sent == []


def test_delivery_log_failure_does_not_break_notify():
    """留痕失敗不可反過來弄丟通知。"""

    class _BoomDeliveries:
        def record(self, *a, **k):
            raise RuntimeError("db down")

    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory(["g1"]), router, deliveries=_BoomDeliveries())
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []), "我胸口悶")
    assert [g for _, g, _ in router.sent] == ["g1"]


def test_no_guardians_no_push(caplog):
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory([]), router)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.9, "求救", []), "救命")
    assert router.sent == []
    assert any("查無可通知家屬" in r.message for r in caplog.records)
    # 原話是對話內容，查無家屬的 log 也不可印（2026-07-27 政策）。
    assert all("救命" not in r.message for r in caplog.records)


def test_absolute_keyword_message_mentions_119_plain_l2_does_not():
    """✅ D-72（己-4）：L3 刪除後，119 提示改掛「絕對危急詞命中」訊號。"""
    router = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.9, "想不開", ["keyword:absolute"]), "我想不開"
    )
    text_absolute = router.sent[0][2]
    assert "119" in text_absolute and "醫療診斷" in text_absolute

    router2 = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router2).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.7, "頭暈", ["keyword:symptom"]), "我有點頭暈"
    )
    assert "119" not in router2.sent[0][2]


def test_single_guardian_unreachable_isolated():
    router = _SpyRouter(fail_on="g1")
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "跌倒", []), "我跌倒了")
    assert [g for _, g, _ in router.sent] == ["g2"]


def test_directory_failure_does_not_raise(caplog):
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory([], raises=True), router)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.9, "求救", []), "救命")
    assert router.sent == []
