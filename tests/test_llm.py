import pytest

from kinsun.llm import (
    GeminiClient,
    LLMClient,
    LLMError,
    Message,
    ToolCall,
    ToolResult,
    ToolSpec,
    _to_contents,
)


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


# --- Gemini 工具呼叫 thought_signature 回帶（gemini-3 thinking 模型必需）---


def _weather_spec() -> ToolSpec:
    return ToolSpec(name="get_weather", description="天氣", parameters={"type": "object"})


class _FakeResp:
    """模擬 GenerateContentResponse：暴露 candidates/function_calls/text。"""

    def __init__(self, parts, text):
        from google.genai import types

        self.candidates = [types.Candidate(content=types.Content(role="model", parts=parts))]
        fcs = [p.function_call for p in parts if p.function_call is not None]
        self.function_calls = fcs or None
        self.text = text


class _FakeGenAI:
    """模擬 genai.Client：records 每次 generate_content 的 contents。"""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.last_contents = None
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.last_contents = contents
        return self._responses.pop(0)


def _find_function_call_signature(contents, name):
    """在送回模型的 contents 中，找出指定 function_call part 的 thought_signature。"""
    for item in contents:
        parts = item.parts if hasattr(item, "parts") else item.get("parts", [])
        for p in parts or []:
            fc = p.function_call if hasattr(p, "function_call") else p.get("function_call")
            fc_name = None
            if fc is not None:
                fc_name = fc.name if hasattr(fc, "name") else fc.get("name")
            if fc_name == name:
                return (
                    p.thought_signature
                    if hasattr(p, "thought_signature")
                    else p.get("thought_signature")
                )
    return "NOT_FOUND"


def test_generate_tool_turn_captures_thought_signature():
    from google.genai import types

    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    part = types.Part(
        function_call=types.FunctionCall(name="get_weather", args={"location": "台北"}),
        thought_signature=b"SIG-1",
    )
    client._client = _FakeGenAI(_FakeResp(parts=[part], text=None))

    turn = client.generate_tool_turn(
        system_prompt="s",
        messages=[Message("user", "天氣")],
        tools=[_weather_spec()],
        tool_results=[],
    )

    assert turn.tool_calls[0].name == "get_weather"
    assert turn.tool_calls[0].thought_signature == b"SIG-1"


def test_generate_tool_turn_echoes_thought_signature_back():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="台北晴，多喝水"))
    client._client = fake

    tr = ToolResult(
        ToolCall("get_weather", {"location": "台北"}, thought_signature=b"SIG-1"),
        "晴 25°C",
    )
    turn = client.generate_tool_turn(
        system_prompt="s",
        messages=[Message("user", "天氣")],
        tools=[_weather_spec()],
        tool_results=[tr],
    )

    assert turn.text == "台北晴，多喝水"
    assert _find_function_call_signature(fake.last_contents, "get_weather") == b"SIG-1"
