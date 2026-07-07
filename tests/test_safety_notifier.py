import logging

from kinsun.accounts.models import ElderGuardian, PrincipalType, Role
from kinsun.safety.notifier import GuardianNotifier, LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-1", RiskAssessment(RiskTier.L3, 0.9, "求救", ["keyword:absolute"]))
    assert any("L3" in r.message and "e-1" in r.message for r in caplog.records)


class _SpyRouter:
    """ChannelRouter 替身：記錄 (principal_type, principal_id, text)，可指定失敗對象。"""

    def __init__(self, fail_on=None):
        self.sent = []
        self._fail_on = fail_on

    def send_text(self, principal_type, principal_id, text):
        if principal_id == self._fail_on:
            return 0  # 該家屬無可達通道／全數失敗
        self.sent.append((principal_type, principal_id, text))
        return 1


def _eg(guardian_id, order):
    return ElderGuardian("e-elder", guardian_id, Role.GUARDIAN, order, False)


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


def test_no_guardians_no_push(caplog):
    router = _SpyRouter()
    notifier = GuardianNotifier(_StubDirectory([]), router)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("e-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert router.sent == []
    assert any("查無可通知家屬" in r.message for r in caplog.records)


def test_l3_message_mentions_119_l2_does_not():
    router = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router).notify(
        "e-elder", RiskAssessment(RiskTier.L3, 0.9, "想不開", [])
    )
    text_l3 = router.sent[0][2]
    assert "119" in text_l3 and "醫療診斷" in text_l3

    router2 = _SpyRouter()
    GuardianNotifier(_StubDirectory(["g1"]), router2).notify(
        "e-elder", RiskAssessment(RiskTier.L2, 0.7, "頭暈", [])
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
        notifier.notify("e-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert router.sent == []
