"""危急偵測關鍵詞（placeholder）。

⚠️ 以下詞表為 placeholder，需照護專業與實測定稿，見
docs/危急偵測與誤報處理設計.md §10。
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
)

# 命中至少 L2
SYMPTOM_WORDS = (
    "頭暈",
    "跌倒",
    "一直痛",
    "好幾天沒睡",
    "沒力氣",
)


def classify_keywords(text: str) -> tuple[RiskTier, bool]:
    if any(word in text for word in ABSOLUTE_DANGER_WORDS):
        return RiskTier.L2, True
    if any(word in text for word in SYMPTOM_WORDS):
        return RiskTier.L2, False
    return RiskTier.L0, False
