"""危急偵測：合併關鍵詞與 LLM，後端複核 → RiskAssessment。"""

from __future__ import annotations

from kinsun.safety.classifier import RiskClassifier
from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier


class RiskDetector:
    """三級制（✅ D-72，己-4）：單一降級門檻 mid——純 LLM 判 L2 但信心不足降 L1；
    關鍵詞（絕對詞與症狀詞）撐住的 L2 不受門檻影響。"""

    def __init__(self, classifier: RiskClassifier, *, mid: float = 0.4) -> None:
        self._classifier = classifier
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
            return RiskAssessment(RiskTier.L2, llm.confidence, "命中絕對危急詞", signals)

        final = max(kw_tier, llm.tier)
        if final == RiskTier.L2 and llm.confidence < self._mid and kw_tier < RiskTier.L2:
            final = RiskTier.L1
        # ✅ D-31（甲-5）fail-safe：分級器故障（例外或回傳無法解析）且句子非空時，
        # 不再靜默 L0——保守記 L1 供留痕（pipeline 落庫不通知）。關鍵詞命中者不受影響。
        if "llm:error" in llm.signals and text.strip() and final < RiskTier.L1:
            return RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON, signals)
        return RiskAssessment(final, llm.confidence, llm.reason, signals)
