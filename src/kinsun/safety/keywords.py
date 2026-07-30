"""危急偵測關鍵詞。

詞表版本：2026-07-13 納入 D-32 AI 候選詞全數 35 詞（Leo 核定，庚-47）——
placeholder 11 詞 → 46 詞；60 句標注集評測數字見 16_WBS 庚-47。
後續仍依會-6「實測滾動擴充」；比對為字面包含，變形講法須獨立列。
"""

from __future__ import annotations

from kinsun.safety.tiers import RiskTier

# 命中即直接 L2 頂級（規則 override，不受信心門檻影響；✅ D-72 三級制）
ABSOLUTE_DANGER_WORDS = (
    "救命",
    "喘不過氣",
    "胸口很痛",
    "昏倒",
    "想不開",
    "不想活",
    # ── D-32 候選詞（2026-07-13 納入）──
    "胸痛",
    "胸口痛",
    "胸口悶",
    "心臟很痛",
    "不能呼吸",
    "呼吸困難",
    "快喘不過來",
    "暈倒",
    "叫不醒",
    "失去意識",
    "想死",
    "自殺",
    "活不下去",
    "不如死了算了",
    "叫救護車",
    "打119",
    "快來救我",
    "嘴歪",
    "半邊麻",
    "講話大舌頭",
    "手腳麻掉不能動",
    "流血不止",
    "血流不停",
)

# 命中至少 L2
SYMPTOM_WORDS = (
    "頭暈",
    "跌倒",
    "一直痛",
    "好幾天沒睡",
    "沒力氣",
    # ── D-32 候選詞（2026-07-13 納入）──
    "頭很暈",
    "天旋地轉",
    "摔倒",
    "滑倒",
    "爬不起來",
    "站不起來",
    "一直吐",
    "發燒",
    "心悸",
    "心跳很快",
    "吃不下",
    "走不動",
)


# 地端偵測器（`local_detector.py`）：把字面比對升級成「比對＋守門」。
#   關掉即完全回到下方 `_legacy_classify` 的原始行為——這是回退路徑，
#   兩個詞表常數也因此保留不動（`strategies/policy.py` 與測試仍在使用）。
_USE_LOCAL_DETECTOR = True


def _legacy_classify(text: str) -> tuple[RiskTier, bool]:
    """原始的純字面比對（2026-07-30 前的行為），保留為回退路徑。"""
    if any(word in text for word in ABSOLUTE_DANGER_WORDS):
        return RiskTier.L2, True
    if any(word in text for word in SYMPTOM_WORDS):
        return RiskTier.L2, False
    return RiskTier.L0, False


def classify_keywords(text: str) -> tuple[RiskTier, bool]:
    """回 (tier, is_emergency)。

    ⚠️ 第二個值的語意在 2026-07-30 換掉了：舊語意是「絕對詞，分級器不得翻案」，
    新語意是「**家屬簡訊要不要附 119 提示**」——純文案，不影響分級。
    翻案機制連同絕對詞旗標一起移除，理由見 `detector.RiskDetector` docstring。

    ## 為什麼改用地端偵測器（2026-07-30）

    字面比對讀不懂否定、人稱、時態與引述，那正是 `detector.py` docstring
    記錄的四種誤報的成因——原本靠分級器事後翻案補救，現在在比對當下就擋掉。

    kinsun 自己的 60 句標注集（`data/safety_eval/labeled_utterances.jsonl`）：

    | | 應通報 27 句，漏掉 | 不該通報 33 句，誤報 |
    | --- | --- | --- |
    | 原本的 46 詞 | 13 | 7 |
    | 地端偵測器 | **6** | **1** |

    另在 219 句**兩邊都沒看過**的真危機語料上（來源與本專案標注集無關）：
    原本的 46 詞接住 7.3%，地端偵測器 68.5%。代價是真人語料誤報率
    0.09% → 0.37%（6,691 句一般看板）、0.58% → 1.37%（1,895 句憂鬱症看板）。
    """
    if not _USE_LOCAL_DETECTOR:
        return _legacy_classify(text)
    from kinsun.safety.local_detector import screen

    return screen(text)
