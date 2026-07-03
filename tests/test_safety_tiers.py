from kinsun.safety.tiers import RiskAssessment, RiskTier


def test_tiers_are_ordered():
    assert RiskTier.L3 > RiskTier.L2 > RiskTier.L1 > RiskTier.L0
    assert max(RiskTier.L1, RiskTier.L3) == RiskTier.L3


def test_assessment_defaults_signals_empty():
    a = RiskAssessment(RiskTier.L0, 0.0, "ok")
    assert a.signals == []
    assert a.tier == RiskTier.L0
