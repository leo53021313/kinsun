import json

from kinsun.knowledge.facts import FactCategory, Provenance
from kinsun.llm import LLMError, Message
from kinsun.longterm.extractor import ConsolidationExtractor, _parse_consolidation


def test_parse_both_facts_and_episodes():
    raw = json.dumps(
        {
            "facts": [
                {
                    "category": "condition",
                    "content": "高血壓",
                    "provenance": "self_claimed",
                    "confidence": 0.6,
                }
            ],
            "episodes": ["想念孫子"],
        }
    )
    c = _parse_consolidation("u1", raw)
    assert len(c.facts) == 1
    assert c.facts[0].category == FactCategory.CONDITION
    assert c.facts[0].provenance == Provenance.SELF_CLAIMED
    assert c.episodes == ["想念孫子"]


def test_parse_bad_json_is_empty():
    c = _parse_consolidation("u1", "抱歉沒有")
    assert c.facts == []
    assert c.episodes == []


def test_parse_missing_keys_and_fallbacks():
    raw = json.dumps(
        {"facts": [{"category": "weird", "content": "x", "provenance": "hearsay", "confidence": 2}]}
    )
    c = _parse_consolidation("u1", raw)
    assert c.facts[0].category == FactCategory.OTHER
    assert c.facts[0].provenance == Provenance.INFERRED
    assert c.facts[0].confidence == 1.0
    assert c.episodes == []


def test_parse_skips_invalid_entries():
    raw = json.dumps(
        {"facts": [{"category": "event", "confidence": 0.5}], "episodes": ["好的", "", 123]}
    )
    c = _parse_consolidation("u1", raw)
    assert c.facts == []
    assert c.episodes == ["好的"]


class _StubLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return json.dumps({"facts": [], "episodes": ["長者表達對孫子的思念"]})


def test_extract_returns_consolidation():
    c = ConsolidationExtractor(_StubLLM()).extract("u1", [Message("user", "我好想孫子")])
    assert c.episodes == ["長者表達對孫子的思念"]


def test_extract_empty_messages():
    c = ConsolidationExtractor(_StubLLM()).extract("u1", [])
    assert c.facts == [] and c.episodes == []


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("boom")


def test_extract_failsafe_on_llm_error():
    c = ConsolidationExtractor(_BoomLLM()).extract("u1", [Message("user", "x")])
    assert c.facts == [] and c.episodes == []
