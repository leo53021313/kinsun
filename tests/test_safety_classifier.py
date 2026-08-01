from kinsun.llm import LLMError, Message
from kinsun.safety.classifier import LlmRiskClassifier, _parse_classification
from kinsun.safety.tiers import RiskTier


def test_parse_valid_json():
    a = _parse_classification('{"tier": 2, "confidence": 0.9, "reason": "求救"}')
    assert a.tier == RiskTier.L2
    assert a.confidence == 0.9
    assert a.reason == "求救"
    assert a.signals == ["llm"]


def test_parse_json_in_markdown_fence():
    a = _parse_classification('```json\n{"tier": 2, "confidence": 0.5, "reason": "痛"}\n```')
    assert a.tier == RiskTier.L2


def test_parse_bad_json_is_failsafe():
    a = _parse_classification("抱歉我無法判斷")
    assert a.tier == RiskTier.L0
    assert a.confidence == 0.0
    assert a.signals == ["llm:error"]


def test_parse_clamps_out_of_range():
    """✅ D-72（己-4）：三級制上限 L2——模型若照舊制吐 3 也夾回 L2。"""
    a = _parse_classification('{"tier": 7, "confidence": 2.5, "reason": "x"}')
    assert a.tier == RiskTier.L2
    assert a.confidence == 1.0


def test_prompt_only_offers_three_tiers():
    from kinsun.safety.classifier import CLASSIFY_SYSTEM_PROMPT

    assert "0-2" in CLASSIFY_SYSTEM_PROMPT
    assert "3 立即" not in CLASSIFY_SYSTEM_PROMPT


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message], response_schema=None) -> str:
        raise LLMError("boom")


def test_classify_attaches_safety_prompt(monkeypatch):
    """危急分級把 CLASSIFY_SYSTEM_PROMPT 註冊/連結到 trace（方案 A：程式碼為真相）。"""
    from kinsun import tracing
    from kinsun.safety.classifier import CLASSIFY_SYSTEM_PROMPT

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tracing, "attach_prompt", lambda name, content: calls.append((name, content))
    )
    LlmRiskClassifier(_BoomLLM()).classify("我不太舒服")
    assert ("safety_classify", CLASSIFY_SYSTEM_PROMPT) in calls


def test_classifier_failsafe_on_llm_error():
    a = LlmRiskClassifier(_BoomLLM()).classify("救命")
    assert a.tier == RiskTier.L0
    assert a.signals == ["llm:error"]


class _StubLLM:
    def generate(self, *, system_prompt: str, messages: list[Message], response_schema=None) -> str:
        return '{"tier": 1, "confidence": 0.3, "reason": "情緒低落"}'


def test_classifier_returns_parsed():
    a = LlmRiskClassifier(_StubLLM()).classify("我好孤單")
    assert a.tier == RiskTier.L1
    assert a.reason == "情緒低落"


def test_classify_requests_structured_output():
    """危急分級走受控生成（response_schema），降低格式故障導致的 L0 假陰性。"""
    from kinsun.safety.classifier import _CLASSIFY_SCHEMA

    captured = {}

    class _CapturingLLM:
        def generate(self, *, system_prompt, messages, response_schema=None):
            captured["schema"] = response_schema
            return '{"tier": 0, "confidence": 0.1, "reason": "ok"}'

    LlmRiskClassifier(_CapturingLLM()).classify("你好")
    assert captured["schema"] == _CLASSIFY_SCHEMA


class _CapturingLLM:
    """記下送出的訊息，讓「脈絡有沒有真的進 prompt」測得出來。"""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def generate(self, *, system_prompt, messages, response_schema=None):
        self.messages = messages
        return '{"tier": 0, "confidence": 0.9, "reason": "ok"}'


def test_classify_without_context_sends_only_the_sentence():
    """沒有脈絡時逐字不變——回歸防線，確保加脈絡沒有動到既有那條路。"""
    llm = _CapturingLLM()
    LlmRiskClassifier(llm).classify("今天天氣真好")
    assert [(m.role, m.content) for m in llm.messages] == [("user", "今天天氣真好")]


def test_classify_puts_earlier_utterances_in_front_of_the_sentence():
    """把同一段對話稍早的話一起送進去，並講明要分級的是最後那一句。

    2026-08-01 正式環境實況：長輩連說兩句「想去西方極樂世界」都正確判 L2、通報了
    家屬；第三句「為什麼一定要找家人 而不是要找你」卻判 tier=0、confidence=0.95，
    理由寫「使用者為情緒互動或對AI的定位產生好奇」。那句話單獨看確實無害——
    分級器看不到前兩句，於是一個正在表達自傷意念的人被判成對 AI 好奇。
    """
    llm = _CapturingLLM()
    LlmRiskClassifier(llm).classify(
        "為什麼一定要找家人 而不是要找你",
        recent=["最近我朋友的阿嬤過世了 我好難過喔", "我要去西方極樂世界囉"],
    )
    sent = llm.messages[0].content
    assert "我要去西方極樂世界囉" in sent
    assert "最近我朋友的阿嬤過世了 我好難過喔" in sent
    # 要分級的是最後那一句，不是整段——講不清楚會讓模型改去分級稍早那句。
    assert sent.rindex("為什麼一定要找家人 而不是要找你") > sent.rindex("我要去西方極樂世界囉")
    assert "只是脈絡" in sent


def test_classify_ignores_blank_context_entries():
    """空字串（主動關懷那一輪的原話刻意設為空）不該在脈絡裡佔一行變成雜訊。"""
    llm = _CapturingLLM()
    LlmRiskClassifier(llm).classify("我好累", recent=["", "  ", "昨天沒睡好"])
    sent = llm.messages[0].content
    assert "昨天沒睡好" in sent
    assert not [line for line in sent.split("\n") if not line.strip()]


def test_classify_falls_back_to_the_plain_sentence_when_context_is_all_blank():
    """脈絡整批是空的，就不要憑空長出一個空的脈絡段落。"""
    llm = _CapturingLLM()
    LlmRiskClassifier(llm).classify("我好累", recent=["", "  "])
    assert [(m.role, m.content) for m in llm.messages] == [("user", "我好累")]
