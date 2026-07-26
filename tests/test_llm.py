from types import SimpleNamespace

import pytest

from kinsun.llm import (
    GeminiClient,
    LLMClient,
    LLMError,
    LLMUsage,
    Message,
    ToolCall,
    ToolResult,
    ToolSpec,
    _to_contents,
    collect_llm_usage,
    report_llm_usage,
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
        self.last_config = None
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.last_contents = contents
        self.last_config = config
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


# --- 結構化輸出（response_schema → 受控生成）---


def test_generate_passes_response_json_schema_when_given():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text='{"tier": 1, "confidence": 0.3, "reason": "x"}'))
    client._client = fake
    schema = {
        "type": "object",
        "properties": {"tier": {"type": "integer"}},
        "required": ["tier"],
    }

    out = client.generate(
        system_prompt="s", messages=[Message("user", "嗨")], response_schema=schema
    )

    assert out == '{"tier": 1, "confidence": 0.3, "reason": "x"}'
    assert fake.last_config.response_json_schema == schema
    assert fake.last_config.response_mime_type == "application/json"


def test_generate_omits_response_config_without_schema():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="一般聊天回覆"))
    client._client = fake

    client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert fake.last_config.response_json_schema is None
    assert fake.last_config.response_mime_type is None


# --- LLM 用量收集（✅ D-05 戊-2：token 用量落庫的量測 seam）---


def test_collect_llm_usage_accumulates_reports():
    usage = LLMUsage()
    with collect_llm_usage(usage):
        report_llm_usage(100, 20)
        report_llm_usage(50, 10)
    assert (usage.input_tokens, usage.output_tokens) == (150, 30)


def test_report_llm_usage_without_collector_is_noop():
    report_llm_usage(1, 1)  # 無收集器時靜默略過，不可丟例外


def test_collector_stops_counting_after_exit():
    usage = LLMUsage()
    with collect_llm_usage(usage):
        pass
    report_llm_usage(5, 5)
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


def test_generate_reports_usage_metadata():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    resp = _FakeResp(parts=[], text="好")
    resp.usage_metadata = SimpleNamespace(
        prompt_token_count=120, candidates_token_count=8, thoughts_token_count=32
    )
    client._client = _FakeGenAI(resp)
    usage = LLMUsage()
    with collect_llm_usage(usage):
        client.generate(system_prompt="s", messages=[Message("user", "嗨")])
    # 輸出 token＝候選＋思考（thinking 模型的思考也計費為輸出）。
    assert (usage.input_tokens, usage.output_tokens) == (120, 40)


def test_generate_tool_turn_reports_usage_metadata():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    resp = _FakeResp(parts=[], text="台北晴")
    resp.usage_metadata = SimpleNamespace(prompt_token_count=200, candidates_token_count=15)
    client._client = _FakeGenAI(resp)
    usage = LLMUsage()
    with collect_llm_usage(usage):
        client.generate_tool_turn(
            system_prompt="s",
            messages=[Message("user", "天氣")],
            tools=[_weather_spec()],
            tool_results=[],
        )
    assert (usage.input_tokens, usage.output_tokens) == (200, 15)


def test_generate_without_usage_metadata_records_nothing():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    client._client = _FakeGenAI(_FakeResp(parts=[], text="好"))
    usage = LLMUsage()
    with collect_llm_usage(usage):
        client.generate(system_prompt="s", messages=[Message("user", "嗨")])
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


def test_gemini_client_applies_client_wrapper():
    marker = object()
    seen = {}

    def wrapper(client):
        seen["inner"] = client
        return marker

    client = GeminiClient(api_key="dummy", model="m", timeout=30.0, client_wrapper=wrapper)
    assert client._client is marker
    assert seen["inner"] is not None  # 底層 genai.Client 有被建出來並傳入


def test_gemini_client_without_wrapper_keeps_native_client():
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    assert client._client is not None


def test_gemini_client_applies_the_configured_timeout():
    """`GEMINI_TIMEOUT_SECONDS` 必須真的送到 SDK（2026-07-26 延遲實測）。

    先前 `timeout` 只存進 `self._timeout` 就沒下文，等於 Gemini 呼叫**沒有任何
    客戶端逾時**：生產資料 llm_calls p95 11.5s、max 23.8s，實測還撞過單輪 46 秒與
    52 秒（同批其他次都在 7～8 秒）。對照組 ASR／TTS 的逾時確實生效，兩者的
    latency 精準卡在設定值（15s／30s）——差別就在有沒有把值傳下去。

    SDK 的 `HttpOptions.timeout` 單位是**毫秒**，設定檔是秒，故換算不可省。
    """
    client = GeminiClient(api_key="dummy", model="m", timeout=12.5)

    assert client._client._api_client._http_options.timeout == 12500
