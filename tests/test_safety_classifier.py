from kinsun.llm import LLMError, Message
from kinsun.safety.classifier import LlmRiskClassifier, _parse_classification
from kinsun.safety.tiers import RiskTier


def test_parse_valid_json():
    a = _parse_classification('{"tier": 3, "confidence": 0.9, "reason": "求救"}')
    assert a.tier == RiskTier.L3
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
    a = _parse_classification('{"tier": 7, "confidence": 2.5, "reason": "x"}')
    assert a.tier == RiskTier.L3
    assert a.confidence == 1.0


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("boom")


def test_classifier_failsafe_on_llm_error():
    a = LlmRiskClassifier(_BoomLLM()).classify("救命")
    assert a.tier == RiskTier.L0
    assert a.signals == ["llm:error"]


class _StubLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return '{"tier": 1, "confidence": 0.3, "reason": "情緒低落"}'


def test_classifier_returns_parsed():
    a = LlmRiskClassifier(_StubLLM()).classify("我好孤單")
    assert a.tier == RiskTier.L1
    assert a.reason == "情緒低落"
