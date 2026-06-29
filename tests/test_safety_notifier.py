import logging

from kinsun.safety.notifier import LineGuardianNotifier, LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-1", RiskAssessment(RiskTier.L3, 0.9, "求救", ["keyword:absolute"]))
    assert any("L3" in r.message and "U-1" in r.message for r in caplog.records)


class _SpyPusher:
    def __init__(self, fail_on=None):
        self.calls = []
        self._fail_on = fail_on

    def push_text(self, user_id, text):
        if user_id == self._fail_on:
            raise RuntimeError("push failed")
        self.calls.append((user_id, text))


class _StubDirectory:
    def __init__(self, line_ids, *, raises=False):
        self._line_ids = line_ids
        self._raises = raises

    def guardian_line_ids(self, elder_line_id):
        if self._raises:
            raise RuntimeError("db down")
        return list(self._line_ids)


def test_pushes_to_all_guardians_in_order():
    pusher = _SpyPusher()
    notifier = LineGuardianNotifier(_StubDirectory(["g1", "g2"]), pusher)
    notifier.notify("U-elder", RiskAssessment(RiskTier.L2, 0.8, "胸口悶", ["symptom"]))
    assert [c[0] for c in pusher.calls] == ["g1", "g2"]
    assert "胸口悶" in pusher.calls[0][1]


def test_no_guardians_no_push(caplog):
    pusher = _SpyPusher()
    notifier = LineGuardianNotifier(_StubDirectory([]), pusher)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert pusher.calls == []
    assert any("查無可通知家屬" in r.message for r in caplog.records)


def test_l3_message_mentions_119_l2_does_not():
    pusher = _SpyPusher()
    LineGuardianNotifier(_StubDirectory(["g1"]), pusher).notify(
        "U-elder", RiskAssessment(RiskTier.L3, 0.9, "想不開", [])
    )
    text_l3 = pusher.calls[0][1]
    assert "119" in text_l3 and "醫療診斷" in text_l3

    pusher2 = _SpyPusher()
    LineGuardianNotifier(_StubDirectory(["g1"]), pusher2).notify(
        "U-elder", RiskAssessment(RiskTier.L2, 0.7, "頭暈", [])
    )
    assert "119" not in pusher2.calls[0][1]


def test_single_push_failure_isolated():
    pusher = _SpyPusher(fail_on="g1")
    notifier = LineGuardianNotifier(_StubDirectory(["g1", "g2"]), pusher)
    notifier.notify("U-elder", RiskAssessment(RiskTier.L2, 0.8, "跌倒", []))
    assert [c[0] for c in pusher.calls] == ["g2"]


def test_directory_failure_does_not_raise(caplog):
    pusher = _SpyPusher()
    notifier = LineGuardianNotifier(_StubDirectory([], raises=True), pusher)
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-elder", RiskAssessment(RiskTier.L3, 0.9, "求救", []))
    assert pusher.calls == []
