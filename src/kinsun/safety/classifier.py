"""LLM 危急分級器：專用結構化呼叫，輸出 {tier, confidence, reason}。"""

from __future__ import annotations

import json
from typing import Protocol

from kinsun.llm import LLMClient, LLMError, Message
from kinsun.safety.tiers import RiskAssessment, RiskTier

CLASSIFY_SYSTEM_PROMPT = (
    "你是長者照護的安全分級器。判斷使用者這句話的危急程度，"
    '只輸出 JSON：{"tier": 0-3, "confidence": 0-1, "reason": "簡短理由"}。'
    "tier 定義：0 一般；1 情緒或健康弱訊號；2 明確但非立即危險（持續疼痛、疑似漏藥、輕微跌倒）；"
    "3 立即生命危險（求救、胸痛呼吸困難、意識不清、自傷意念）。"
    "注意區分身體不適與情緒因素，避免把口頭誇飾誤判為危急。只輸出 JSON，不要多餘文字。"
)

_FAILSAFE_REASON = "llm 無法判定"
_FAILSAFE_SIGNALS = ["llm:error"]


class RiskClassifier(Protocol):
    def classify(self, text: str) -> RiskAssessment: ...


def _extract_json(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("找不到 JSON 物件", raw, 0)
    return raw[start : end + 1]


def _parse_classification(raw: str) -> RiskAssessment:
    try:
        data = json.loads(_extract_json(raw))
        tier = RiskTier(max(0, min(3, int(data["tier"]))))
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return RiskAssessment(RiskTier.L0, 0.0, _FAILSAFE_REASON, list(_FAILSAFE_SIGNALS))
    return RiskAssessment(tier, confidence, reason, ["llm"])


class LlmRiskClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def classify(self, text: str) -> RiskAssessment:
        try:
            raw = self._llm.generate(
                system_prompt=CLASSIFY_SYSTEM_PROMPT, messages=[Message("user", text)]
            )
        except LLMError:
            return RiskAssessment(RiskTier.L0, 0.0, _FAILSAFE_REASON, list(_FAILSAFE_SIGNALS))
        return _parse_classification(raw)
