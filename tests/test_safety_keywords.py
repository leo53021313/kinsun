from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import RiskTier


def test_absolute_danger_word_is_l2_top_with_flag():
    """✅ D-72（己-4）：絕對危急詞改判 L2 頂級，仍以 absolute 旗標區別（不受門檻降級）。"""
    tier, absolute = classify_keywords("救命啊我喘不過氣")
    assert tier == RiskTier.L2
    assert absolute is True


def test_symptom_word_is_l2_without_flag():
    tier, absolute = classify_keywords("我今天有點頭暈")
    assert tier == RiskTier.L2
    assert absolute is False


def test_clean_text_is_l0():
    tier, absolute = classify_keywords("今天天氣真好")
    assert tier == RiskTier.L0
    assert absolute is False
