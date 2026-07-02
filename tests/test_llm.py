import pytest

from kinsun.llm import GeminiClient, LLMClient, LLMError, Message, _to_contents


def test_empty_api_key_raises():
    with pytest.raises(LLMError):
        GeminiClient(api_key="", model="gemini-2.5-flash", timeout=30.0)


def test_to_contents_maps_roles():
    out = _to_contents([Message("user", "嗨"), Message("assistant", "你好")])
    assert out == [
        {"role": "user", "parts": [{"text": "嗨"}]},
        {"role": "model", "parts": [{"text": "你好"}]},
    ]


def test_fake_satisfies_protocol():
    class FakeLLM:
        def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
            return f"回應：{messages[-1].content}"

    client: LLMClient = FakeLLM()
    assert client.generate(system_prompt="s", messages=[Message("user", "嗨")]) == "回應：嗨"
