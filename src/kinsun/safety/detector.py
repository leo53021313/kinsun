"""危急偵測：合併關鍵詞與 LLM，後端複核 → RiskAssessment。"""

from __future__ import annotations

from kinsun.safety.classifier import RiskClassifier
from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import RiskAssessment, RiskTier


class RiskDetector:
    def __init__(self, classifier: RiskClassifier, *, high: float = 0.7, mid: float = 0.4) -> None:
        self._classifier = classifier
        self._high = high
        self._mid = mid

    def assess(self, text: str) -> RiskAssessment:
        kw_tier, kw_absolute = classify_keywords(text)
        try:
            llm = self._classifier.classify(text)
        except Exception:  # noqa: BLE001 - 偵測絕不可中斷對話
            llm = RiskAssessment(RiskTier.L0, 0.0, "分級器例外", ["llm:error"])

        signals: list[str] = []
        if kw_tier > RiskTier.L0:
            signals.append("keyword:absolute" if kw_absolute else "keyword:symptom")
        signals.extend(llm.signals)

        if kw_absolute:
            return RiskAssessment(RiskTier.L3, llm.confidence, "命中絕對危急詞", signals)

        final = max(kw_tier, llm.tier)
        if final == RiskTier.L3 and llm.confidence < self._high and kw_tier < RiskTier.L3:
            final = RiskTier.L2
        if final == RiskTier.L2 and llm.confidence < self._mid and kw_tier < RiskTier.L2:
            final = RiskTier.L1
        return RiskAssessment(final, llm.confidence, llm.reason, signals)
