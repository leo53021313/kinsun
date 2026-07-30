from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import RiskTier


def test_emergency_utterance_is_l2_with_flag():
    """✅ D-72（己-4）：求救判 L2 頂級，並掛 emergency 旗標（家屬簡訊附 119 提示）。"""
    tier, emergency = classify_keywords("救命啊我喘不過氣")
    assert tier == RiskTier.L2
    assert emergency is True


def test_symptom_word_is_l2_without_flag():
    """症狀詞照樣 L2 通報，但不附 119——那不是叫救護車的情境。"""
    tier, emergency = classify_keywords("我今天有點頭暈")
    assert tier == RiskTier.L2
    assert emergency is False


def test_clean_text_is_l0():
    tier, emergency = classify_keywords("今天天氣真好")
    assert tier == RiskTier.L0
    assert emergency is False


def test_the_four_classic_false_positives_are_l0():
    """★ 換成地端偵測器的收穫之一：字面比對讀不懂的四種話，現在判 L0。

    舊的 46 詞字面比對這四句全判 L2 —— 家屬手機真的會收到警報。
    """
    for text in (
        "你放心啦，我沒有跌倒，好好的",
        "我十年前跌倒過一次，現在都好了",
        "隔壁的陳太太昨天跌倒送醫院了",
        "老人家要怎麼預防跌倒？",
    ):
        assert classify_keywords(text)[0] == RiskTier.L0, text


def test_crisis_wording_outside_the_legacy_word_list_is_caught():
    """★ 收穫之二：真危機的講法遠多於 46 個詞。

    這幾句沒有命中任何一個 `ABSOLUTE_DANGER_WORDS`／`SYMPTOM_WORDS`，
    舊的字面比對全判 L0 —— 完全不通知家屬。
    """
    for text in (
        "我在陽台，想從這裡跳下去",
        "藥我全部吞下去了，想說一次解決",
        "半邊臉麻麻的，嘴巴歪歪講不清楚",
        "我把瓦斯打開了，不想再撐了",
    ):
        assert classify_keywords(text)[0] == RiskTier.L2, text
