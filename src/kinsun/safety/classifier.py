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
    "注意區分身體不適與情緒因素，避免把口頭誇飾誤判為危急。"
    # 沒有這一句，模型收到脈絡段之後會把「稍早那句已經很嚴重了」誤讀成「這一句也嚴重」
    # 或反過來只看最後一句的字面。講明用途：脈絡是用來理解這一句的，不是拿來一起判。
    "若訊息裡附了長輩稍早說過的話，那只是幫你理解最後那一句的脈絡——"
    "分級的對象永遠是最後那一句，但要把前面的話讀進去再判"
    "（例如前面剛表達過自傷意念，後面一句看似平常的追問仍應視為同一件事的延續）。"
    "只輸出 JSON，不要多餘文字。"
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
    def classify(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment: ...


# 脈絡段的框：兩句話都是承重的。前一句擋「模型改去分級稍早那句」（前面那幾句往往
# 更聳動，一起送進去而不講清楚要判哪一句，等於把分級目標交給模型自己選）；後一句
# 是分級目標的錨。⚠️ 兩句都被 test_classify_puts_earlier_utterances_in_front 釘住。
_CONTEXT_HEADER = "（以下是同一段對話裡長輩稍早說過的話，只是脈絡，不要分級這幾句）"
_TARGET_HEADER = "（要分級的是下面這一句）"


def _with_context(text: str, recent: list[str] | None) -> str:
    """把稍早的原話疊在待分級句之前；沒有可用脈絡時逐字回傳原句。

    2026-08-01 正式環境實況：長輩連說兩句「想去西方極樂世界」都判 L2、通報了家屬，
    第三句「為什麼一定要找家人 而不是要找你」判 tier=0／confidence=0.95，理由是
    「對AI的定位產生好奇」。那一句單獨看確實無害——分級器一次只收到一句話，看不到
    前兩句，於是一個正在表達自傷意念的人被判成好奇。

    ⚠️ 只放長輩自己說的話，不放金孫的回覆：金孫的安撫話術（「聽了真讓人好擔心」）
    帶著危急詞彙，混進去會讓分級器對著自己的話升級——與 `strategies/reflection.py`
    的 `_split_ungrounded_address` 防的是同一種自我增強迴圈。

    空字串要濾掉：主動關懷那一輪把長輩原話刻意設為空（見 `agent.proactive`），
    原樣疊上去會變成一行空白雜訊。整批都空就退回原句，不長出空的段落。
    """
    lines = [line.strip() for line in (recent or []) if line and line.strip()]
    if not lines:
        return text
    return "\n".join([_CONTEXT_HEADER, *lines, _TARGET_HEADER, text])


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

    def classify(self, text: str, *, recent: list[str] | None = None) -> RiskAssessment:
        tracing.attach_prompt("safety_classify", CLASSIFY_SYSTEM_PROMPT)
        try:
            raw = self._llm.generate(
                system_prompt=CLASSIFY_SYSTEM_PROMPT,
                messages=[Message("user", _with_context(text, recent))],
                response_schema=_CLASSIFY_SCHEMA,
            )
        except LLMError:
            return RiskAssessment(RiskTier.L0, 0.0, FAILSAFE_REASON, list(FAILSAFE_SIGNALS))
        return _parse_classification(raw)
