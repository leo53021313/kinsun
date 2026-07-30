"""LLM 危急分級器：專用結構化呼叫，輸出 {tier, confidence, reason}。"""

from __future__ import annotations

import json
from typing import Protocol

from kinsun import tracing
from kinsun.llm import LLMClient, LLMError, Message
from kinsun.safety.tiers import RiskAssessment, RiskTier

# 三級制（✅ D-72，己-4）：L2 為頂級——立即危險與明確警訊都判 2，由家屬接手判斷。
CLASSIFY_SYSTEM_PROMPT = (
    "你是長者照護的安全分級器。判斷使用者這句話的危急程度，"
    '只輸出 JSON：{"tier": 0-2, "confidence": 0-1, "reason": "簡短理由"}。'
    "tier 定義：0 一般；1 情緒或健康弱訊號（如最近睡不好、心情低落）；"
    "2 明確警訊（持續疼痛、跌倒、疑似漏藥、求救、胸痛呼吸困難、意識不清、自傷意念）。"
    "注意區分身體不適與情緒因素，避免把口頭誇飾誤判為危急。只輸出 JSON，不要多餘文字。"
)

FAILSAFE_REASON = "llm 無法判定"
FAILSAFE_SIGNALS = ["llm:error"]

# 受控生成 schema：讓模型被約束為合法 JSON，減少「格式故障→fail-safe 誤退 L0」的
# 危急假陰性。schema 只約束結構、不約束語意，tier 的 0-2 定義仍靠 CLASSIFY_SYSTEM_PROMPT。
_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "integer"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["tier", "confidence", "reason"],
}


class RiskClassifier(Protocol):
    def classify(self, text: str) -> RiskAssessment: ...


def _extract_json(raw: str) -> str:
    # 縱深防禦：response_schema 已約束模型輸出合法 JSON，此撈殼（第一個 { 到最後一個 }）
    # 刻意保留——這是危急分級器，即使受控生成偶爾失常，仍寧可撈回也不要誤退 L0。
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("找不到 JSON 物件", raw, 0)
    return raw[start : end + 1]


def _parse_classification(raw: str) -> RiskAssessment:
    try:
        data = json.loads(_extract_json(raw))
        tier = RiskTier(max(0, min(2, int(data["tier"]))))  # 舊制吐 3 也夾回 L2
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return RiskAssessment(RiskTier.L0, 0.0, FAILSAFE_REASON, list(FAILSAFE_SIGNALS))
    return RiskAssessment(tier, confidence, reason, ["llm"])


class LlmRiskClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def classify(self, text: str) -> RiskAssessment:
        tracing.attach_prompt("safety_classify", CLASSIFY_SYSTEM_PROMPT)
        try:
            raw = self._llm.generate(
                system_prompt=CLASSIFY_SYSTEM_PROMPT,
                messages=[Message("user", text)],
                response_schema=_CLASSIFY_SCHEMA,
            )
        except LLMError:
            return RiskAssessment(RiskTier.L0, 0.0, FAILSAFE_REASON, list(FAILSAFE_SIGNALS))
        return _parse_classification(raw)
