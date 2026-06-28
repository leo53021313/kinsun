import logging

from kinsun.safety.notifier import LogNotifier
from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_log_notifier_logs_warning(caplog):
    notifier = LogNotifier()
    with caplog.at_level(logging.WARNING, logger="kinsun.safety"):
        notifier.notify("U-1", RiskAssessment(RiskTier.L3, 0.9, "求救", ["keyword:absolute"]))
    assert any("L3" in r.message and "U-1" in r.message for r in caplog.records)
