import logging

from kinsun.accounts.models import ElderGuardian, PrincipalType, Role
from kinsun.safety.deliveries import FakeRiskNotificationLogStore
from kinsun.safety.notifier import GuardianNotifier, LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-1", RiskAssessment(RiskTier.L2, 0.9, "求救", ["keyword:absolute"]))
    assert any("L2" in r.message and "e-1" in r.message for r in caplog.records)


class _SpyRouter:
    """ChannelRouter 替身：記錄 (principal_type, principal_id, text)，可指定失敗對象。"""

    def __init__(self, fail_on=None, channels=("line",)):
        self.sent = []
        self._fail_on = fail_on
        self._channels = list(channels)

    def send_text_channels(self, principal_type, principal_id, text):
        if principal_id == self._fail_on:
            return []  # 該家屬無可達通道／全數失敗
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
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]))
    assert [(t, g) for t, g, _ in router.sent] == [
        (PrincipalType.GUARDIAN, "g1"),
        (PrincipalType.GUARDIAN, "g2"),
    ]
    assert "胸口悶" in router.sent[0][2]


def test_delivery_log_records_success_and_failure_per_guardian():
    """✅ D-36（丙-7）：每位家屬的送達與否獨立留痕——「當時有沒有收到」查得到。"""
    router = _SpyRouter(fail_on="g2")
    deliveries = FakeRiskNotificationLogStore()
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router, deliveries=deliveries)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]))
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
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]))
    assert deliveries.recorded[0].channels == "app"

    router2 = _SpyRouter(channels=("line", "app"))
    deliveries2 = FakeRiskNotificationLogStore()
    GuardianNotifier(_StubDirectory(["g1"]), router2, deliveries=deliveries2).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", [])
    )
    assert deliveries2.recorded[0].channels == "line,app"


def test_delivery_log_failure_does_not_break_notify():
    """留痕失敗不可反過來弄丟通知。"""

    class _BoomDeliveries:
        def record(self, *a, **k):
            raise RuntimeError("db down")

    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory(["g1"]), router, deliveries=_BoomDeliveries())
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", []))
    assert [g for _, g, _ in router.sent] == ["g1"]


def test_no_guardians_no_push(caplog):
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory([]), router)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.9, "求救", []))
    assert router.sent == []
    assert any("查無可通知家屬" in r.message for r in caplog.records)


def test_absolute_keyword_message_mentions_119_plain_l2_does_not():
    """✅ D-72（己-4）：L3 刪除後，119 提示改掛「絕對危急詞命中」訊號。"""
    router = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.9, "想不開", ["keyword:absolute"])
    )
    text_absolute = router.sent[0][2]
    assert "119" in text_absolute and "醫療診斷" in text_absolute

    router2 = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router2).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.7, "頭暈", ["keyword:symptom"])
    )
    assert "119" not in router2.sent[0][2]


def test_single_guardian_unreachable_isolated():
    router = _SpyRouter(fail_on="g1")
    notifier = GuardianNotifier(_StubDirectory(["g1", "g2"]), router)
    notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.8, "跌倒", []))
    assert [g for _, g, _ in router.sent] == ["g2"]


def test_directory_failure_does_not_raise(caplog):
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory([], raises=True), router)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-elder", RiskAssessment(RiskTier.L2, 0.9, "求救", []))
    assert router.sent == []
