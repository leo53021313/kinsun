from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import RiskTier


def test_absolute_danger_word_is_l3():
    tier, absolute = classify_keywords("救命啊我喘不過氣")
    assert tier == RiskTier.L3
    assert absolute is True


def test_symptom_word_is_at_least_l2():
    tier, absolute = classify_keywords("我今天有點頭暈")
    assert tier == RiskTier.L2
    assert absolute is False


def test_clean_text_is_l0():
    tier, absolute = classify_keywords("今天天氣真好")
    assert tier == RiskTier.L0
    assert absolute is False
