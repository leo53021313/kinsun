from kinsun.safety.detector import RiskDetector
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier


class FakeClassifier:
    def __init__(self, assessment: RiskAssessment) -> None:
        self._a = assessment

    def classify(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        return self._a


def _llm(tier, conf):
    return RiskAssessment(tier, conf, "r", ["llm"])


def test_emergency_keyword_overrides_even_if_llm_low():
    """✅ D-72（己-4）：求救直判 L2 頂級，不受信心門檻影響。

    `keyword:emergency` 訊號同時決定家屬簡訊要不要附 119 提示
    （見 `notifier._format_alert`）。
    """
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, 0.0)))
    got = det.assess("救命")
    assert got.tier == RiskTier.L2
    assert "keyword:emergency" in got.signals


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
    def classify(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
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


# ── 關鍵詞層是地板，分級器只能往上加（2026-07-30 取代「症狀詞翻案」）──
# 翻案是 2026-07-26 為了修四種誤報（否定／陳年往事／第三人稱／衛教提問）而加的。
# 那四種現在由關鍵詞層的守門在**比對當下**就擋掉，翻案已無事可翻，故整段移除。
# 本節改為守住新的不變式：**任何分級器判定都不得把關鍵詞層撐起來的等級拉低。**

CONFIDENT = 0.9  # 分級器很有把握
UNSURE = 0.2  # 沒把握
BARELY = 0.5  # 過得了 mid（0.4）但仍不足以動搖地板


def test_the_four_real_world_false_positives_never_reach_the_keyword_floor():
    """實測抓到的四種誤報形態：否定、陳年往事、第三人稱、衛教提問。

    ⚠️ 這裡用**故障的**分級器：這四句在關鍵詞層就判 L0，不需要任何 LLM 幫忙。
    舊設計做不到這件事——它要等一個「沒故障且有把握」的分級器才翻得掉，
    Gemini 掛掉的那半小時這四句照樣通知家屬。
    """
    det = RiskDetector(_BoomClassifier())
    for text in (
        "你放心啦，我沒有跌倒，好好的",
        "我十年前跌倒過一次，那時候住院一個月，現在都好了",
        "隔壁的陳太太昨天跌倒送醫院了，好可憐",
        "老人家要怎麼預防跌倒？",
    ):
        assert det.assess(text).tier < RiskTier.L2, text


def test_no_classifier_verdict_can_pull_the_keyword_floor_down():
    """★ 核心不變式：關鍵詞層判 L2 之後，分級器說什麼都拉不下來。

    三種它可能說的話全試一次——沒把握、勉強有把握、非常有把握地說沒事。
    """
    for confidence in (UNSURE, BARELY, CONFIDENT):
        det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, confidence)))
        assert det.assess("我剛剛跌倒了").tier == RiskTier.L2, confidence


def test_a_confident_classifier_cannot_overturn_a_crisis_utterance():
    """求死意念是紅線：分級器再有把握也拉不下來。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, CONFIDENT)))
    for text in ("我不想活了", "我喘不過氣", "快叫救護車"):
        assert det.assess(text).tier == RiskTier.L2, text


def test_a_confident_classifier_that_says_l2_still_alerts():
    """真的跌倒不會因為這條改動而漏掉——分級器判 L2 就是 L2。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L2, CONFIDENT)))
    assert det.assess("我剛剛在浴室跌倒了，爬不起來").tier == RiskTier.L2


def test_the_classifier_can_still_raise_a_tier():
    """只升不降：關鍵詞層沒看到的東西，分級器照樣拉得起來。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L2, CONFIDENT)))
    assert det.assess("今天天氣真好").tier == RiskTier.L2


def test_a_weak_signal_from_the_classifier_still_alerts_the_family():
    """分級器判 L1（它自己也覺得有小訊號）時，關鍵詞層的 L2 照舊通報。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L1, CONFIDENT)))
    assert det.assess("我這幾天有點頭暈").tier == RiskTier.L2


def test_a_broken_classifier_cannot_pull_down_a_keyword_floor_even_if_it_sounds_sure():
    """⚠️ 紅線回歸：分級器故障時回傳的 confidence 是垃圾值（可能是解析失敗前的殘值），
    不得因為它自稱 0.99 就把已經亮起的安全地板關掉。
    """
    broken = RiskAssessment(RiskTier.L0, 0.99, "分級器例外", ["llm:error"])
    det = RiskDetector(FakeClassifier(broken))
    got = det.assess("我剛剛跌倒了")
    assert got.tier == RiskTier.L2
    assert "keyword:emergency" in got.signals
