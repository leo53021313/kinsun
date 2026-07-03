# CareAgent 工具呼叫（含 Open-Meteo 天氣工具）設計

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：④ Agent 核心「②呼叫工具」、⑤ 工具/外部服務。
> 前置：[端到端語音薄切片]、[記憶層雲端遷移](2026-06-29-記憶層雲端遷移-design.md)。
> 借鏡來源：hermes-agent `agent/conversation_loop.py`、`tools/registry.py`（取極簡版；本機 `temp/` 參考、不進版控）。
> Gemini function calling API：google-genai（`/googleapis/python-genai`）`types.FunctionDeclaration`/`Tool`、`response.function_calls`、`Part.from_function_response`。
> 本案為「Hermes / Mem0 借鏡與優化」系列第 5 項（T3.4）。

---

## 1. 背景與目標

[CareAgent](../../../src/kinsun/agent.py) 目前是單次 LLM 呼叫、無工具，無法查天氣/新聞等外部資訊（架構圖④「②呼叫工具」未實現）。本案讓 CareAgent 支援 **Gemini function calling 的多輪工具迴圈**，並附一個真實工具 **Open-Meteo 天氣查詢**驗證端到端。

**完成後：** 長者問「今天台北天氣？」→ 模型呼叫 `get_weather` → 取 Open-Meteo 即時天氣 → 模型用口語回覆。框架就緒後，新增工具只需註冊一個 handler。

**設計原則：** 借鏡 hermes 的迴圈與 registry，但**只抄極簡版**；迴圈放在 agent（可離線測），`GeminiClient` 只做「中性型別 ↔ genai 型別」翻譯；無工具時走原路（向後相容）；全程 fail-safe。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 中性工具型別（`ToolSpec`/`ToolCall`/`ToolResult`/`ToolTurn`，置 `llm.py`）。
* `LLMClient` Protocol 新增 `generate_tool_turn`；`GeminiClient` 實作（genai 翻譯）。`generate` 不動。
* `tools/registry.py`：`ToolRegistry`（register / specs / dispatch，dispatch 永不拋）。
* `tools/weather.py`：Open-Meteo 天氣工具（`get_weather(location)`），HTTP 走 stdlib `urllib`，fetch 可注入。
* `CareAgent` 工具迴圈（建構新增 `tools`、`max_tool_iters=3`；無工具走原路）。
* `app.py` 接線：建 registry、註冊天氣工具、注入 CareAgent。
* 離線單元測試（registry、agent loop、weather 解析）。

### 2.2 不在範圍內（YAGNI／後續）
* **新聞/衛教 RAG/MCP/plugin/subagent/concurrent dispatch/prompt cache**（hermes 有，太重）。
* **proactive 走工具**（系統主動訊息維持單次 generate）。
* **`GeminiClient.generate_tool_turn` 的離線單元測**（genai 翻譯層，與既有 `generate` 同樣 manual/整合驗證）。
* 天氣工具新增環境變數/金鑰（Open-Meteo 免金鑰）。

---

## 3. 元件與介面

### 3.1 中性型別（llm.py）
```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON schema（properties/required）

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict

@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    output: str

@dataclass(frozen=True)
class ToolTurn:
    text: str | None
    tool_calls: list[ToolCall]   # 空 = 已是最終文字
```

### 3.2 LLM Protocol 與 GeminiClient（llm.py）
```python
class LLMClient(Protocol):
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str: ...
    def generate_tool_turn(
        self, *, system_prompt: str, messages: list[Message],
        tools: list[ToolSpec], tool_results: list[ToolResult],
    ) -> ToolTurn: ...
```
`GeminiClient.generate_tool_turn`：
* 以 `_to_contents(messages)` 為基底；對每個 `tool_results` 追加 genai 的 function_call content（`types.Part(function_call=types.FunctionCall(name, args))`，role=model）與 function_response content（`types.Part.from_function_response(name, {"result": output})`，role=tool）。
* `tools` → `types.Tool(function_declarations=[types.FunctionDeclaration(name, description, parameters_json_schema=spec.parameters), ...])`。
* `generate_content(model, contents, config=GenerateContentConfig(system_instruction=..., tools=[tool]))`。
* `response.function_calls` 非空 → `ToolTurn(None, [ToolCall(fc.name, dict(fc.args)) ...])`；否則 `ToolTurn(response.text, [])`。空文字比照 `generate` 拋 `LLMError`（由 webhook 接住）。

### 3.3 工具註冊表（tools/registry.py）
```python
class ToolRegistry:
    def register(self, spec: ToolSpec, handler: Callable[[dict], str]) -> None
    def specs(self) -> list[ToolSpec]
    def dispatch(self, name: str, arguments: dict) -> str:
        # 找不到工具 → "（找不到工具：{name}）"
        # handler 例外 → logger.exception + "（工具執行失敗，請稍後再試）"
        # 永不拋例外
```

### 3.4 天氣工具（tools/weather.py）
```python
WEATHER_SPEC = ToolSpec(
    name="get_weather",
    description="查詢指定地點今天的天氣（概況與氣溫）。",
    parameters={"type": "object",
                "properties": {"location": {"type": "string", "description": "地點名稱，例：台北、高雄"}},
                "required": ["location"]},
)

def build_weather_handler(fetch_json: Callable[[str], dict] = _urllib_fetch_json) -> Callable[[dict], str]:
    # location 空 → 友善提示
    # geocoding（地名→經緯度，無結果 → 友善提示）
    # forecast（current temperature_2m + weather_code；daily 高/低溫）
    # weather_code → 中文（_WMO 對照，未知 → "天氣"）
    # 回 "台北今天多雲，氣溫約 22–28°C，目前 25°C。"
```
* HTTP：`urllib.request`（同 [DgxAsrClient](../../../src/kinsun/speech/asr.py)），逾時 10s；`_urllib_fetch_json(url) -> dict`。
* Open-Meteo：`geocoding-api.open-meteo.com/v1/search`、`api.open-meteo.com/v1/forecast`（`timezone=Asia/Taipei`、`forecast_days=1`）。
* 網路/解析例外**不自行吞**：由 `ToolRegistry.dispatch` 統一接住回友善字串（保留例外可觀測性於 dispatch log）。

### 3.5 CareAgent 迴圈（agent.py）
```python
FALLBACK_REPLY = "金孫剛剛想了一下沒講清楚，您可以再說一次嗎？"

class CareAgent:
    def __init__(self, llm, memory, context, *, tools=None, max_tool_iters=3) -> None: ...

    def handle(self, session_id, user_text) -> str:
        system_prompt = SYSTEM_PROMPT + self._context.recall(session_id, user_text)
        base = [*self._memory.recent(session_id), Message("user", user_text)]
        if self._tools is None:
            reply = self._llm.generate(system_prompt=system_prompt, messages=base)   # 原路、零變更
        else:
            reply = self._run_tool_loop(system_prompt, base)
        self._memory.append(session_id, Message("user", user_text))
        self._memory.append(session_id, Message("assistant", reply))
        return reply

    def _run_tool_loop(self, system_prompt, base) -> str:
        results: list[ToolResult] = []
        for _ in range(self._max_tool_iters):
            turn = self._llm.generate_tool_turn(
                system_prompt=system_prompt, messages=base,
                tools=self._tools.specs(), tool_results=results)
            if not turn.tool_calls:
                return turn.text or FALLBACK_REPLY
            for call in turn.tool_calls:
                results.append(ToolResult(call, self._tools.dispatch(call.name, call.arguments)))
        return FALLBACK_REPLY        # loop 用盡（防無限）
```
`proactive` 不變（維持單次 `generate`）。

### 3.6 接線（app.py）
```python
from kinsun.tools.registry import ToolRegistry
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler

registry = ToolRegistry()
registry.register(WEATHER_SPEC, build_weather_handler())
... agent=CareAgent(gemini, memory, context, tools=registry) ...
```

---

## 4. 資料流
```
長者語音 → VoicePipeline → CareAgent.handle（有 tools）
  → loop#1 generate_tool_turn → 模型回 function_call get_weather{location:"台北"}
       → registry.dispatch → Open-Meteo geocode+forecast → "台北今天多雲 22–28°C"
  → loop#2 generate_tool_turn（帶 tool_results）→ 模型回口語文字 → 回長者
```

## 5. 錯誤處理（fail-safe 各層）
* `dispatch`：工具不存在/handler 例外 → 回友善字串、記 log、**不拋**。
* 天氣 API 網路/解析失敗 → 例外傳到 dispatch 接住 → 友善字串；模型照常回應。
* `max_tool_iters=3` 防無限迴圈；用盡回 `FALLBACK_REPLY`。
* `generate_tool_turn` 空回應/呼叫失敗 → `LLMError`（webhook 既有 try/except 退化為 FALLBACK_PROMPT）。
* 無 `tools` → 走原 `generate` 路徑，行為與測試零變更。

## 6. 測試策略（邏輯離線測；genai 翻譯層 manual）
* `tests/test_tools_registry.py`：register/specs；dispatch 正常回字串；找不到工具回友善字串；handler 拋例外 → 友善字串、不拋。
* `tests/test_agent.py`（新增，沿用 SpyLLM 風格擴充 `generate_tool_turn`）：
  * 工具迴圈：FakeLLM 先回 `ToolTurn(tool_calls=[get_weather])`、再回 `ToolTurn(text=...)` → agent 呼叫 registry、回最終文字；記憶只存 user+assistant（不存中間工具）。
  * loop 上限：FakeLLM 永遠回 tool_calls → 達 `max_tool_iters` 回 `FALLBACK_REPLY`。
  * 無工具向後相容：既有三測試不變（`tools=None` 走 `generate`）。
* `tests/test_weather_tool.py`：注入假 `fetch_json` 回罐頭 geocode+forecast → 驗回傳含地點/溫度/概況；地點查無 → 友善字串；空 location → 友善字串。
* **不離線測**：`GeminiClient.generate_tool_turn`（genai 翻譯，manual/整合；與既有 `GeminiClient.generate` 一致）。
* 全套 `uv run pytest` 綠、ruff 綠。

## 7. 已知取捨（列出供否決）
* **迴圈在 agent、GeminiClient 只翻譯**：risky 邏輯離線可測；genai 翻譯層 manual 驗（與現況一致）。
* **天氣兩次 fetch（geocode+forecast）**：Open-Meteo 免金鑰的代價；逾時 10s、fail-safe。
* **`max_tool_iters=3`**：小 bot 不需深層工具鏈；用盡回 fallback。
* **新增 `tools/` 套件**：與既有 `safety/`、`scheduler/` 同層的功能分組，符合現有結構。
* **天氣工具的真實呼叫待手動/整合驗證**：離線測證「解析與 fail-safe 正確」，真實 Open-Meteo 回應待手動冒煙。
