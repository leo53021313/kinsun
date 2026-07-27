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


# ── 症狀詞翻案（2026-07-26 全流程模擬實測）──
# 症狀詞是字面比對，讀不懂否定、時態與主詞；分級器讀得懂。實測 12 筆風險事件中
# 4 筆是誤報且**真的送到家屬手機**，故有把握的分級器可以把症狀詞從 L2 翻到 L1
# （留痕進每日摘要、不響警報）。絕對詞與分級器故障兩條紅線不動。

CONFIDENT = 0.9  # ≥ 翻案門檻（0.7）＝分級器很有把握
UNSURE = 0.2  # 沒把握，不准翻案
BARELY = 0.5  # 過得了 mid（0.4）但過不了翻案門檻（0.7）——刻意的不對稱


def test_confident_classifier_downgrades_a_symptom_keyword_to_l1():
    """「我沒有跌倒」不該吵到家屬——分級器有把握說不危急時，症狀詞降為留痕。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, CONFIDENT)))
    got = det.assess("你放心啦，我沒有跌倒，好好的")
    assert got.tier == RiskTier.L1  # 落庫留痕、不通知家屬
    assert "keyword:symptom" in got.signals


def test_the_four_real_world_false_positives_no_longer_alert_the_family():
    """實測抓到的四種誤報形態：否定、陳年往事、第三人稱、衛教提問。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, CONFIDENT)))
    for text in (
        "你放心啦，我沒有跌倒，好好的",
        "我十年前跌倒過一次，那時候住院一個月，現在都好了",
        "隔壁的陳太太昨天跌倒送醫院了，好可憐",
        "老人家要怎麼預防跌倒？",
    ):
        assert det.assess(text).tier < RiskTier.L2, text


def test_an_unsure_classifier_cannot_overturn_a_symptom_keyword():
    """沒把握就不准翻案：維持原本的保守判定，寧可誤報也不漏報。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, UNSURE)))
    assert det.assess("我剛剛跌倒了").tier == RiskTier.L2


def test_barely_confident_is_not_enough_to_turn_off_a_safety_floor():
    """⚠️ 刻意的不對稱：翻案門檻（0.7）高於 mid（0.4）。

    `mid` 管的是「要不要相信一個 L2 判定」，猜錯只是多吵家屬一次；
    這裡管的是「要不要把已經亮起的安全地板關掉」，猜錯就是漏掉一次真的求救。
    """
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, BARELY)))
    assert det.assess("我剛剛跌倒了").tier == RiskTier.L2


def test_a_confident_classifier_still_cannot_overturn_an_absolute_word():
    """絕對詞是紅線：分級器再有把握也不能翻。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, CONFIDENT)))
    for text in ("我不想活了", "我喘不過氣", "快叫救護車"):
        assert det.assess(text).tier == RiskTier.L2, text


def test_a_confident_classifier_that_says_l2_still_alerts():
    """真的跌倒不會因為這條改動而漏掉——分級器判 L2 就是 L2。"""
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L2, CONFIDENT)))
    assert det.assess("我剛剛在浴室跌倒了，爬不起來").tier == RiskTier.L2


def test_an_overturned_symptom_keyword_lands_on_l1_not_l0():
    """翻案落在 L1（留痕不通知），不掉到 L0。

    長輩確實講了症狀詞，這件事要留給每日摘要（✅ D-10 己-5）。
    """
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L0, CONFIDENT)))
    assert det.assess("我這幾天有點頭暈").tier == RiskTier.L1


def test_a_weak_signal_from_the_classifier_still_alerts_the_family():
    """⚠️ 只准 L0 翻案：分級器判 L1（它自己也覺得有小訊號）時照舊通報。

    標注集實測：允許 L1 翻案會新漏掉「我好幾天沒睡，眼睛都花了」（L1／0.95）與
    「最近都沒力氣，連菜都提不動」（L1／0.90）——兩句的標注都是應通報。
    """
    det = RiskDetector(FakeClassifier(_llm(RiskTier.L1, CONFIDENT)))
    assert det.assess("我這幾天有點頭暈").tier == RiskTier.L2


def test_a_broken_classifier_cannot_overturn_a_symptom_keyword_even_if_it_sounds_sure():
    """⚠️ 紅線回歸：`llm:error` 期間不准翻案，分級器自報的信心再高也不行。

    故障時回傳的 confidence 是垃圾值（可能是解析失敗前的殘值），若不看 signals，
    一個「故障但自稱很有把握」的判定就能把安全地板整個關掉。
    拿掉 detector 裡的 `"llm:error" not in llm.signals` 這一行，本測試即紅。
    """
    broken = RiskAssessment(RiskTier.L0, 0.99, "分級器例外", ["llm:error"])
    det = RiskDetector(FakeClassifier(broken))
    got = det.assess("我剛剛跌倒了")
    assert got.tier == RiskTier.L2
    assert "keyword:symptom" in got.signals
