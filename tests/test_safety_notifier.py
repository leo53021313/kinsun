import logging

from kinsun.safety.notifier import LineGuardianNotifier, LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-1", RiskAssessment(RiskTier.L3, 0.9, "求救", ["keyword:absolute"]))
    assert any("L3" in r.message and "U-1" in r.message for r in caplog.records)


class _SpyChannel:
    def __init__(self, fail_on=None):
        self.sent = []
        self._fail_on = fail_on

    def send_text(self, elder_id, text):
        if elder_id == self._fail_on:
            raise RuntimeError("push failed")
        self.sent.append((elder_id, text))


class _StubDirectory:
    def __init__(self, line_ids, *, raises=False):
        self._line_ids = line_ids
        self._raises = raises

    def guardian_line_ids_of_elder(self, elder_id):
        if self._raises:
            raise RuntimeError("db down")
        return list(self._line_ids)


def test_pushes_to_all_guardians_in_order():
    channel = _SpyChannel()
    notifier = LineGuardianNotifier(_StubDirectory(["g1", "g2"]), channel)
    notifier.notify("U-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]))
    assert [c[0] for c in channel.sent] == ["g1", "g2"]
    assert "胸口悶" in channel.sent[0][1]


def test_no_guardians_no_push(caplog):
    channel = _SpyChannel()
    notifier = LineGuardianNotifier(_StubDirectory([]), channel)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert channel.sent == []
    assert any("查無可通知家屬" in r.message for r in caplog.records)


def test_l3_message_mentions_119_l2_does_not():
    channel = _SpyChannel()
    LineGuardianNotifier(_StubDirectory(["g1"]), channel).notify(
        "U-elder", RiskAssessment(RiskTier.L3, 0.9, "想不開", [])
    )
    text_l3 = channel.sent[0][1]
    assert "119" in text_l3 and "醫療診斷" in text_l3

    channel2 = _SpyChannel()
    LineGuardianNotifier(_StubDirectory(["g1"]), channel2).notify(
        "U-elder", RiskAssessment(RiskTier.L2, 0.7, "頭暈", [])
    )
    assert "119" not in channel2.sent[0][1]


def test_single_push_failure_isolated():
    channel = _SpyChannel(fail_on="g1")
    notifier = LineGuardianNotifier(_StubDirectory(["g1", "g2"]), channel)
    notifier.notify("U-elder", RiskAssessment(RiskTier.L2, 0.8, "跌倒", []))
    assert [c[0] for c in channel.sent] == ["g2"]


def test_directory_failure_does_not_raise(caplog):
    channel = _SpyChannel()
    notifier = LineGuardianNotifier(_StubDirectory([], raises=True), channel)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert channel.sent == []
