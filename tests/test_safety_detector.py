from kinsun.safety.detector import RiskDetector
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier


class FakeClassifier:
    def __init__(self, assessment: RiskAssessment) -> None:
        self._a = assessment

    def classify(self, text: str) -> RiskAssessment:
        return self._a


def _llm(tier, conf):
    return RiskAssessment(tier, conf, "r", ["llm"])


def test_absolute_keyword_overrides_even_if_llm_low():
    """✅ D-72（己-4）：絕對詞直判 L2 頂級，不受信心門檻影響。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, 0.0)))
    got = det.assess("救命")
    assert got.tier == RiskTier.L2
    assert "keyword:absolute" in got.signals


def test_takes_max_of_keyword_and_llm():
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L2, 0.9)))
    assert det.assess("今天天氣真好").tier == RiskTier.L2


def test_llm_l2_low_confidence_downgrades_to_l1():
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L2, 0.2)))
    assert det.assess("今天天氣真好").tier == RiskTier.L1


def test_symptom_keyword_floor_not_downgraded():
    # 症狀詞撐 L2；即使 LLM 低信心也不該降到 L1
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, 0.0)))
    assert det.assess("我一直痛").tier == RiskTier.L2


def test_clean_is_l0():
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, 0.9)))
    assert det.assess("今天天氣真好").tier == RiskTier.L0


class _BoomClassifier:
    def classify(self, text: str) -> RiskAssessment:
        raise RuntimeError("boom")


def test_assess_never_raises_on_classifier_error():
    det = RiskDetector(_BoomClassifier())
    assert det.assess("救命").tier == RiskTier.L2


def test_classifier_error_nonempty_text_failsafe_l1():
    """✅ D-31（甲-5）：分級器故障＋非空句 → 保守記 L1 留痕（不再靜默 L0）。"""
    det = RiskDetector(_BoomClassifier())
    got = det.assess("今天天氣真好")
    assert got.tier == RiskTier.L1
    assert got.reason == FAILSAFE_EVENT_REASON
    assert "llm:error" in got.signals


def test_classifier_error_blank_text_stays_l0():
    det = RiskDetector(_BoomClassifier())
    assert det.assess("   ").tier == RiskTier.L0


def test_classifier_error_symptom_keyword_keeps_l2():
    """故障期間關鍵詞仍守門：症狀詞照常 L2（走通知路徑，不降級成留痕）。"""
    det = RiskDetector(_BoomClassifier())
    got = det.assess("我一直痛")
    assert got.tier == RiskTier.L2


def test_symptom_keyword_with_llm_error_reason_reflects_keyword():
    """✅ 庚-41（A-44）：症狀詞撐住的 L2 遇分級器故障，reason 不得寫「分級器例外」
    ——家屬通知文案取 reason，應反映真正觸發原因（關鍵詞）。"""
    detector = RiskDetector(_BoomClassifier())
    got = detector.assess("我今天一直吐")
    assert got.tier is RiskTier.L2
    assert "分級器例外" not in got.reason
    assert "症狀" in got.reason
