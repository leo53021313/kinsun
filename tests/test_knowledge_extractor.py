import json

from kinsun.knowledge.extractor import FactExtractor, _parse_facts
from kinsun.knowledge.facts import FactCategory, Provenance
from kinsun.llm import LLMError, Message


def test_parse_valid_array():
    raw = json.dumps(
        [
            {
                "category": "condition",
                "content": "高血壓",
                "provenance": "self_claimed",
                "confidence": 0.6,
            }
        ]
    )
    facts = _parse_facts("u1", raw)
    assert len(facts) == 1
    assert facts[0].category == FactCategory.CONDITION
    assert facts[0].provenance == Provenance.SELF_CLAIMED


def test_parse_bad_json_is_empty():
    assert _parse_facts("u1", "抱歉沒有事實") == []


def test_parse_unknown_enums_fall_back():
    raw = json.dumps(
        [{"category": "weird", "content": "x", "provenance": "hearsay", "confidence": 2}]
    )
    f = _parse_facts("u1", raw)[0]
    assert f.category == FactCategory.OTHER
    assert f.provenance == Provenance.INFERRED
    assert f.confidence == 1.0


def test_parse_skips_missing_content():
    raw = json.dumps([{"category": "event", "provenance": "inferred", "confidence": 0.5}])
    assert _parse_facts("u1", raw) == []


class _StubLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return json.dumps(
            [
                {
                    "category": "medication",
                    "content": "每天吃血壓藥",
                    "provenance": "self_claimed",
                    "confidence": 0.7,
                }
            ]
        )


def test_extract_returns_facts():
    facts = FactExtractor(_StubLLM()).extract("u1", [Message("user", "我有吃血壓藥")])
    assert facts[0].category == FactCategory.MEDICATION


def test_extract_empty_messages():
    assert FactExtractor(_StubLLM()).extract("u1", []) == []


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("boom")


def test_extract_failsafe_on_llm_error():
    assert FactExtractor(_BoomLLM()).extract("u1", [Message("user", "x")]) == []
