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


def classify_keywords(text: str) -> tuple[RiskTier, bool]:
    if any(word in text for word in ABSOLUTE_DANGER_WORDS):
        return RiskTier.L2, True
    if any(word in text for word in SYMPTOM_WORDS):
        return RiskTier.L2, False
    return RiskTier.L0, False
