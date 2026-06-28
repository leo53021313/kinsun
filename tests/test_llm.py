import pytest

from kinsun.llm import GeminiClient, LLMClient, LLMError


def test_empty_api_key_raises():
    with pytest.raises(LLMError):
        GeminiClient(api_key="", model="gemini-2.5-flash", timeout=30.0)


def test_fake_satisfies_protocol():
    class FakeLLM:
        def generate(self, *, system_prompt: str, user_text: str) -> str:
            return f"回應：{user_text}"

    client: LLMClient = FakeLLM()
    assert client.generate(system_prompt="s", user_text="嗨") == "回應：嗨"
