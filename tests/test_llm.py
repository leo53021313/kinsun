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


def test_tool_turn_asks_the_model_to_think_before_choosing_a_tool():
    """工具回合必須明說思考層級——預設值在 gemini-3.5-flash-lite 上等於不呼叫工具。"""
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="好喔"))
    client._client = fake

    client.generate_tool_turn(
        system_prompt="s",
        messages=[Message("user", "附近哪裡有拉麵")],
        tools=[_weather_spec()],
        tool_results=[],
    )

    assert fake.last_config.thinking_config.thinking_level == "MEDIUM"


def test_plain_generate_does_not_pay_for_thinking():
    """無工具的呼叫（危急分級、審核、摘要）不加思考——它們吃的是延遲，不是工具判斷。"""
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="好喔"))
    client._client = fake

    client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert fake.last_config.thinking_config is None


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


def test_tool_results_go_back_with_a_role_gemini_accepts():
    """工具結果必須以 `user` 角色回帶，不可用 `tool`（2026-07-26 實機驗證）。

    ⚠️ 這條是實測釘死的，不是風格偏好：`gemini-3.5-flash-lite`（.env 的正式模型）
    對 `role="tool"` 直接回 400 `Role 'tool' is not supported`，於是**每一輪用到工具的
    對話都會失敗、退回「金孫剛剛沒聽清楚」**——天氣、衛教 RAG、新聞、排程、查證全中。
    完整往返實測：

    | 模型 | role="tool" | role="user" |
    | gemini-3.1-flash-lite | OK | OK |
    | gemini-3.5-flash-lite | **400** | OK |

    `user` 兩個模型都吃，故選它。⚠️ 請不要「順手改回」語意上更貼切的 `tool`。
    """
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="台北晴"))
    client._client = fake

    client.generate_tool_turn(
        system_prompt="s",
        messages=[Message("user", "天氣")],
        tools=[_weather_spec()],
        tool_results=[ToolResult(ToolCall("get_weather", {"location": "台北"}), "晴 25°C")],
    )

    roles = [getattr(c, "role", None) or c.get("role") for c in fake.last_contents]
    assert "tool" not in roles, f"工具結果用了 gemini-3.5 不接受的 role：{roles}"


# --- 一輪總預算（辛-21）：每次呼叫的逾時不得超過本輪剩下的時間 ---


def _ok_resp(text: str = "好"):
    return SimpleNamespace(text=text, candidates=None, function_calls=None)


def test_without_a_turn_budget_the_call_keeps_the_client_timeout():
    """沒開預算＝行為與加這個功能之前完全相同（排程端、主動關懷走這條）。"""
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_ok_resp())
    client._client = fake

    client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert getattr(fake.last_config, "http_options", None) is None


def test_a_call_is_capped_by_what_is_left_of_the_turn(monkeypatch):
    """剩 8 秒就只准等 8 秒——逐次逾時管得住一次呼叫，管不住三次相加（2026-07-28）。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_ok_resp())
    client._client = fake

    with tc.turn_budget(30.0):
        clock[0] += 22.0
        client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert fake.last_config.http_options.timeout == 8_000


def test_a_generous_budget_does_not_extend_the_client_timeout(monkeypatch):
    """預算只會把逾時**縮短**，不會放寬：30 秒的逾時仍是 30 秒的逾時。"""
    import kinsun.turn_context as tc

    monkeypatch.setattr(tc.time, "monotonic", lambda: 1000.0)
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_ok_resp())
    client._client = fake

    with tc.turn_budget(300.0):
        client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert fake.last_config.http_options.timeout == 30_000


def test_an_exhausted_budget_fails_immediately_without_calling_gemini(monkeypatch):
    """預算用完就不要再打出去了——那通呼叫的答案不管多好都已經來不及給長輩聽。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_ok_resp())
    client._client = fake

    with tc.turn_budget(30.0), pytest.raises(LLMError):
        clock[0] += 31.0
        client.generate(system_prompt="s", messages=[Message("user", "嗨")])

    assert fake.last_config is None  # 完全沒有打出去


def test_the_tool_turn_obeys_the_same_budget(monkeypatch):
    """兩個出口共用同一把預算——漏掉工具回合等於漏掉最慢的那一段。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])
    client = GeminiClient(api_key="dummy", model="m", timeout=30.0)
    fake = _FakeGenAI(_FakeResp(parts=[], text="台北晴"))
    client._client = fake

    with tc.turn_budget(30.0):
        clock[0] += 24.0
        client.generate_tool_turn(
            system_prompt="s",
            messages=[Message("user", "天氣")],
            tools=[_weather_spec()],
            tool_results=[],
        )

    assert fake.last_config.http_options.timeout == 6_000
