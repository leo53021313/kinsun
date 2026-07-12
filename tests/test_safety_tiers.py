from kinsun.safety.tiers import RiskAssessment, RiskTier, tier_from_db


def test_three_tiers_ordered_and_l3_removed():
    """✅ D-72（己-4）：三級制 L0／L1／L2，L2 為頂級；L3 已刪除。"""
    assert RiskTier.L2 > RiskTier.L1 > RiskTier.L0
    assert max(RiskTier.L1, RiskTier.L2) == RiskTier.L2
    assert not hasattr(RiskTier, "L3")


def test_tier_from_db_clamps_legacy_l3_to_l2():
    """四級制時代的舊資料（tier=3）讀出時視為 L2，不炸也不流失。"""
    assert tier_from_db(3) == RiskTier.L2
    assert tier_from_db(2) == RiskTier.L2
    assert tier_from_db(0) == RiskTier.L0


def test_assessment_defaults_signals_empty():
    a = RiskAssessment(RiskTier.L0, 0.0, "ok")
    assert a.signals == []
    assert a.tier == RiskTier.L0
