import json

from kinsun.episodic.extractor import EpisodeExtractor, _parse_episodes
from kinsun.llm import LLMError, Message


def test_parse_valid_array():
    assert _parse_episodes(json.dumps(["想念孫子", "喜歡園藝"])) == ["想念孫子", "喜歡園藝"]


def test_parse_bad_json_is_empty():
    assert _parse_episodes("沒有片段") == []


def test_parse_skips_non_strings_and_blanks():
    assert _parse_episodes(json.dumps(["好的", "", 123])) == ["好的"]


class _StubLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return json.dumps(["長者表達對孫子的思念"])


def test_extract_returns_episodes():
    out = EpisodeExtractor(_StubLLM()).extract([Message("user", "我好想孫子")])
    assert out == ["長者表達對孫子的思念"]


def test_extract_empty_messages():
    assert EpisodeExtractor(_StubLLM()).extract([]) == []


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        raise LLMError("boom")


def test_extract_failsafe_on_llm_error():
    assert EpisodeExtractor(_BoomLLM()).extract([Message("user", "x")]) == []
