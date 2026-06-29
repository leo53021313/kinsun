# CareAgent 工具呼叫（含 Open-Meteo 天氣工具）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 CareAgent 支援 Gemini function-calling 多輪工具迴圈，並附 Open-Meteo 天氣工具驗證端到端。

**Architecture:** 中性工具型別（llm.py）+ `ToolRegistry`（tools/）+ CareAgent 工具迴圈（可離線測）；`GeminiClient` 只做 genai 翻譯（manual 驗證）；無工具時走原 `generate` 路徑（向後相容）。

**Tech Stack:** Python 3.12、google-genai（function calling）、stdlib urllib（Open-Meteo，免金鑰）、pytest。

## Global Constraints

- 一律台灣繁體中文（文件、註解、commit）。
- 最小修改、不新增第三方套件（天氣走 stdlib urllib）；fail-safe（工具/網路失敗回友善字串、不中斷對話）。
- `generate`（既有）不動；新增 `generate_tool_turn`。proactive 不走工具。
- 迴圈邏輯離線單元測；`GeminiClient.generate_tool_turn` 為 genai 翻譯層，與既有 `GeminiClient.generate` 同樣不進離線套件（manual/整合驗證）。
- `max_tool_iters` 預設 3；無工具→走原路、既有測試零變更。
- commit 規範：`feat/fix/docs/refactor/test/chore`，結尾加 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 品質閘門：`uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、pre-commit 全綠。
- 設計依據：[docs/superpowers/specs/2026-06-29-CareAgent工具呼叫-design.md](../specs/2026-06-29-CareAgent工具呼叫-design.md)。

---

### Task 1: 中性工具型別 + ToolRegistry

**Files:**
- Modify: `src/kinsun/llm.py`
- Create: `src/kinsun/tools/__init__.py`、`src/kinsun/tools/registry.py`
- Test: `tests/test_tools_registry.py`

**Interfaces:**
- Produces:
  - llm.py：`ToolSpec(name: str, description: str, parameters: dict)`、`ToolCall(name: str, arguments: dict)`、`ToolResult(call: ToolCall, output: str)`、`ToolTurn(text: str | None, tool_calls: list[ToolCall])`（皆 frozen dataclass）。
  - `kinsun.tools.registry.ToolRegistry`：`register(spec, handler)`、`specs() -> list[ToolSpec]`、`dispatch(name, arguments) -> str`（永不拋）。

- [ ] **Step 1: Write the failing test**

建立 `tests/test_tools_registry.py`：
```python
from kinsun.llm import ToolSpec
from kinsun.tools.registry import ToolRegistry

SPEC = ToolSpec(name="echo", description="回傳輸入", parameters={"type": "object", "properties": {}})


def test_register_and_specs():
    reg = ToolRegistry()
    reg.register(SPEC, lambda args: "ok")
    assert reg.specs() == [SPEC]


def test_dispatch_calls_handler():
    reg = ToolRegistry()
    reg.register(SPEC, lambda args: f"got {args.get('x')}")
    assert reg.dispatch("echo", {"x": 1}) == "got 1"


def test_dispatch_unknown_tool_returns_friendly():
    assert "找不到工具" in ToolRegistry().dispatch("nope", {})


def test_dispatch_handler_exception_returns_friendly():
    reg = ToolRegistry()

    def boom(args):
        raise RuntimeError("boom")

    reg.register(SPEC, boom)
    assert "工具執行失敗" in reg.dispatch("echo", {})  # 不拋
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools_registry.py -v`
Expected: FAIL — `ImportError`（`ToolSpec`／`ToolRegistry` 尚未存在）。

- [ ] **Step 3: 在 llm.py 新增中性型別**

`src/kinsun/llm.py` 既有 `Message` dataclass 之後新增：
```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict


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
    tool_calls: list[ToolCall]
```

- [ ] **Step 4: 建立 tools 套件**

建立 `src/kinsun/tools/__init__.py`（內容單行）：
```python
"""工具層：CareAgent 可呼叫的工具與註冊表。"""
```
建立 `src/kinsun/tools/registry.py`：
```python
"""極簡工具註冊表：註冊工具、產生 specs、dispatch（永不拋）。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.llm import ToolSpec

logger = logging.getLogger("kinsun.tools")


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict], str]] = {}

    def register(self, spec: ToolSpec, handler: Callable[[dict], str]) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def dispatch(self, name: str, arguments: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"（找不到工具：{name}）"
        try:
            return handler(arguments)
        except Exception:  # noqa: BLE001 - 工具失敗不可中斷對話
            logger.exception("工具執行失敗：%s", name)
            return "（工具執行失敗，請稍後再試）"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_tools_registry.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/llm.py src/kinsun/tools/__init__.py src/kinsun/tools/registry.py tests/test_tools_registry.py
git commit -m "feat: 中性工具型別 + 極簡 ToolRegistry（dispatch 永不拋）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: CareAgent 工具迴圈 + LLM Protocol 方法

**Files:**
- Modify: `src/kinsun/llm.py`（Protocol 新增方法宣告）、`src/kinsun/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `ToolSpec`/`ToolCall`/`ToolResult`/`ToolTurn`（Task 1）、`ToolRegistry`（Task 1）。
- Produces:
  - `LLMClient.generate_tool_turn(*, system_prompt, messages, tools: list[ToolSpec], tool_results: list[ToolResult]) -> ToolTurn`（Protocol）。
  - `kinsun.agent.FALLBACK_REPLY`（str）。
  - `CareAgent(llm, memory, context, *, tools: ToolRegistry | None = None, max_tool_iters: int = 3)`；`handle` 有工具走迴圈、無工具走原 `generate`。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_agent.py` 既有 import 下新增：
```python
from kinsun.agent import FALLBACK_REPLY
from kinsun.llm import ToolCall, ToolSpec, ToolTurn
from kinsun.tools.registry import ToolRegistry
```
在檔尾新增 fake 與測試：
```python
class ScriptedToolLLM:
    """依序回傳預設 ToolTurn；有工具時不應呼叫 generate。"""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def generate(self, *, system_prompt, messages):
        raise AssertionError("有工具時不應呼叫 generate")

    def generate_tool_turn(self, *, system_prompt, messages, tools, tool_results):
        self.calls.append(len(tool_results))
        return self._turns.pop(0)


def _registry_with_weather(output="台北今天晴 25°C"):
    reg = ToolRegistry()
    reg.register(
        ToolSpec(name="get_weather", description="天氣", parameters={"type": "object", "properties": {}}),
        lambda args: output,
    )
    return reg


def test_handle_runs_tool_loop_then_returns_text():
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {"location": "台北"})]),
            ToolTurn(text="台北今天晴，記得多喝水", tool_calls=[]),
        ]
    )
    memory = SpyMemory()
    agent = CareAgent(llm, memory, SpyContext(""), tools=_registry_with_weather())
    reply = agent.handle("u1", "今天台北天氣？")
    assert reply == "台北今天晴，記得多喝水"
    assert memory.appended == [
        ("u1", Message("user", "今天台北天氣？")),
        ("u1", Message("assistant", "台北今天晴，記得多喝水")),
    ]
    assert llm.calls == [0, 1]  # 第二輪帶入 1 筆 tool_result


def test_tool_loop_caps_iterations():
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    llm = ScriptedToolLLM([always_tool, always_tool, always_tool])
    agent = CareAgent(llm, SpyMemory(), SpyContext(""), tools=_registry_with_weather(), max_tool_iters=3)
    reply = agent.handle("u1", "天氣")
    assert reply == FALLBACK_REPLY
    assert len(llm.calls) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent.py -v`
Expected: FAIL — `CareAgent` 尚不接受 `tools=` / 無 `FALLBACK_REPLY`（TypeError／ImportError）。

- [ ] **Step 3: llm.py Protocol 新增方法宣告**

`src/kinsun/llm.py` 的 `LLMClient` Protocol 改為：
```python
class LLMClient(Protocol):
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str: ...
    def generate_tool_turn(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_results: list[ToolResult],
    ) -> ToolTurn: ...
```

- [ ] **Step 4: 改 agent.py 加工具迴圈**

`src/kinsun/agent.py`：import 改為
```python
from kinsun.llm import LLMClient, Message, ToolResult
```
在 `_PROACTIVE_DIRECTIVE` 之後新增：
```python
FALLBACK_REPLY = "金孫剛剛想了一下沒講清楚，您可以再說一次嗎？"
```
`CareAgent.__init__` 與 `handle` 改為（`proactive` 不動）：
```python
class CareAgent:
    def __init__(
        self,
        llm: LLMClient,
        memory: MemoryStore,
        context: MemoryContext,
        *,
        tools=None,
        max_tool_iters: int = 3,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._context = context
        self._tools = tools
        self._max_tool_iters = max_tool_iters

    def handle(self, session_id: str, user_text: str) -> str:
        system_prompt = SYSTEM_PROMPT + self._context.recall(session_id, user_text)
        user_msg = Message("user", user_text)
        base = [*self._memory.recent(session_id), user_msg]
        if self._tools is None:
            reply = self._llm.generate(system_prompt=system_prompt, messages=base)
        else:
            reply = self._run_tool_loop(system_prompt, base)
        self._memory.append(session_id, user_msg)
        self._memory.append(session_id, Message("assistant", reply))
        return reply

    def _run_tool_loop(self, system_prompt: str, base: list[Message]) -> str:
        results: list[ToolResult] = []
        for _ in range(self._max_tool_iters):
            turn = self._llm.generate_tool_turn(
                system_prompt=system_prompt,
                messages=base,
                tools=self._tools.specs(),
                tool_results=results,
            )
            if not turn.tool_calls:
                return turn.text or FALLBACK_REPLY
            for call in turn.tool_calls:
                results.append(ToolResult(call, self._tools.dispatch(call.name, call.arguments)))
        return FALLBACK_REPLY
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent.py -v`
Expected: PASS（既有 3 個 + 新 2 個皆綠；既有 `tools=None` 走 `generate`，行為不變）。

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/llm.py src/kinsun/agent.py tests/test_agent.py
git commit -m "feat: CareAgent 工具迴圈（有工具走 loop，無工具走原路）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Open-Meteo 天氣工具

**Files:**
- Create: `src/kinsun/tools/weather.py`
- Test: `tests/test_weather_tool.py`

**Interfaces:**
- Consumes: `ToolSpec`（Task 1）。
- Produces: `WEATHER_SPEC: ToolSpec`（name `"get_weather"`）、`build_weather_handler(fetch_json=...) -> Callable[[dict], str]`。

- [ ] **Step 1: Write the failing test**

建立 `tests/test_weather_tool.py`：
```python
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler

_GEO = {"results": [{"latitude": 25.0, "longitude": 121.5, "name": "Taipei"}]}
_FC = {
    "current": {"temperature_2m": 25.3, "weather_code": 2},
    "daily": {"temperature_2m_max": [28.1], "temperature_2m_min": [22.4]},
}


def _fetcher(geo, fc):
    def fetch(url):
        return geo if "geocoding" in url else fc

    return fetch


def test_weather_spec_name():
    assert WEATHER_SPEC.name == "get_weather"


def test_handler_formats_weather():
    out = build_weather_handler(_fetcher(_GEO, _FC))({"location": "台北"})
    assert "台北" in out
    assert "多雲" in out
    assert "22" in out and "28" in out


def test_handler_empty_location():
    out = build_weather_handler(_fetcher(_GEO, _FC))({"location": "  "})
    assert "哪個地方" in out


def test_handler_location_not_found():
    out = build_weather_handler(_fetcher({"results": []}, _FC))({"location": "不存在地"})
    assert "查不到" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_weather_tool.py -v`
Expected: FAIL — `ImportError`（`kinsun.tools.weather` 尚未存在）。

- [ ] **Step 3: 建立 weather.py**

建立 `src/kinsun/tools/weather.py`：
```python
"""Open-Meteo 天氣查詢工具（免金鑰）。HTTP 走 stdlib urllib，fetch 可注入以利測試。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

from kinsun.llm import ToolSpec

WEATHER_SPEC = ToolSpec(
    name="get_weather",
    description="查詢指定地點今天的天氣（概況與氣溫）。",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string", "description": "地點名稱，例：台北、高雄"}},
        "required": ["location"],
    },
)

_GEOCODE_URL = (
    "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1&language=zh&format=json"
)
_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
    "&timezone=Asia%2FTaipei&forecast_days=1"
)

_WMO = {
    0: "晴朗", 1: "大致晴朗", 2: "局部多雲", 3: "陰天",
    45: "有霧", 48: "有霧",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "下雨", 63: "下雨", 65: "大雨",
    66: "凍雨", 67: "凍雨",
    71: "下雪", 73: "下雪", 75: "大雪",
    80: "陣雨", 81: "陣雨", 82: "強陣雨",
    95: "雷雨", 96: "雷雨", 99: "雷雨夾冰雹",
}


def _urllib_fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - 固定 https Open-Meteo
        return json.loads(response.read().decode("utf-8"))


def build_weather_handler(
    fetch_json: Callable[[str], dict] = _urllib_fetch_json,
) -> Callable[[dict], str]:
    def handler(args: dict) -> str:
        location = (args.get("location") or "").strip()
        if not location:
            return "請告訴我您想查哪個地方的天氣。"
        geo = fetch_json(_GEOCODE_URL.format(name=urllib.parse.quote(location)))
        results = geo.get("results") or []
        if not results:
            return f"查不到「{location}」這個地點的天氣。"
        place = results[0]
        fc = fetch_json(_FORECAST_URL.format(lat=place["latitude"], lon=place["longitude"]))
        current = fc.get("current") or {}
        daily = fc.get("daily") or {}
        desc = _WMO.get(current.get("weather_code"), "天氣")
        now_t = current.get("temperature_2m")
        highs = (daily.get("temperature_2m_max") or [None])[0]
        lows = (daily.get("temperature_2m_min") or [None])[0]
        parts = [f"{location}今天{desc}"]
        if lows is not None and highs is not None:
            parts.append(f"氣溫約 {round(lows)}–{round(highs)}°C")
        if now_t is not None:
            parts.append(f"目前 {round(now_t)}°C")
        return "，".join(parts) + "。"

    return handler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_weather_tool.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/tools/weather.py tests/test_weather_tool.py
git commit -m "feat: Open-Meteo 天氣工具（免金鑰，urllib，fetch 可注入）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: GeminiClient genai 翻譯 + app.py 接線

**Files:**
- Modify: `src/kinsun/llm.py`（`GeminiClient.generate_tool_turn`）、`src/kinsun/app.py`

**Interfaces:**
- Consumes: `ToolSpec`/`ToolCall`/`ToolResult`/`ToolTurn`（Task 1）、`ToolRegistry`（Task 1）、`WEATHER_SPEC`/`build_weather_handler`（Task 3）、`CareAgent(..., tools=...)`（Task 2）。
- Produces: 可服務的 app，CareAgent 已注入天氣工具。

- [ ] **Step 1: 實作 GeminiClient.generate_tool_turn**

`src/kinsun/llm.py` 的 `GeminiClient` 末尾新增（`generate` 不動）：
```python
    def generate_tool_turn(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_results: list[ToolResult],
    ) -> ToolTurn:
        from google.genai import types

        contents = _to_contents(messages)
        for tr in tool_results:
            contents.append(
                {
                    "role": "model",
                    "parts": [{"function_call": {"name": tr.call.name, "args": tr.call.arguments}}],
                }
            )
            contents.append(
                {
                    "role": "tool",
                    "parts": [
                        {"function_response": {"name": tr.call.name, "response": {"result": tr.output}}}
                    ],
                }
            )
        genai_tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name, description=t.description, parameters_json_schema=t.parameters
                )
                for t in tools
            ]
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt, tools=[genai_tool]
                ),
            )
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 LLMError
            raise LLMError(f"Gemini 工具呼叫失敗：{exc}") from exc
        calls = response.function_calls or []
        if calls:
            return ToolTurn(
                text=None,
                tool_calls=[ToolCall(name=c.name, arguments=dict(c.args or {})) for c in calls],
            )
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return ToolTurn(text=text, tool_calls=[])
```
> 註：此為 genai 翻譯層、不進離線測試（同 `GeminiClient.generate`）。`response.function_calls` 項目以 `c.name`／`c.args` 讀取；function_call/function_response contents 以 dict 形式附加——兩者皆為手動冒煙時確認點，若 SDK 細節有出入於此微調。

- [ ] **Step 2: app.py 接線**

`src/kinsun/app.py` import 區新增：
```python
from kinsun.tools.registry import ToolRegistry
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler
```
在 `pipeline = VoicePipeline(` 之前建立 registry：
```python
    registry = ToolRegistry()
    registry.register(WEATHER_SPEC, build_weather_handler())
```
把 `agent=CareAgent(gemini, memory, context)` 改為：
```python
        agent=CareAgent(gemini, memory, context, tools=registry),
```

- [ ] **Step 3: 靜態驗證 + 全套品質閘門**

Run: `PYTHONPATH=src uv run python -c "import kinsun.app, kinsun.llm, kinsun.agent, kinsun.tools.weather; print('ok')"`
Expected: 印出 `ok`（無 import 錯誤）。

Run: `uv run pytest`
Expected: 全部通過（opt-in 整合測試 skip；`GeminiClient.generate_tool_turn` 無離線測但其餘全綠）。

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 無錯誤、皆已格式化。

- [ ] **Step 4: Commit**

```bash
git add src/kinsun/llm.py src/kinsun/app.py
git commit -m "feat: GeminiClient 工具翻譯 + app 注入天氣工具（T3.4 完成）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage：**
- spec §3.1 中性型別 → Task 1 ✅
- spec §3.2 Protocol + GeminiClient → Task 2（Protocol）+ Task 4（GeminiClient）✅
- spec §3.3 ToolRegistry → Task 1 ✅
- spec §3.4 天氣工具 → Task 3 ✅
- spec §3.5 CareAgent 迴圈 → Task 2 ✅
- spec §3.6 app 接線 → Task 4 ✅
- spec §6 測試（registry/agent loop/weather 離線；GeminiClient manual）→ Task 1/2/3 ✅；§6 不離線測項 → Task 4 註明 ✅

**2. Placeholder scan：** 無 TBD/TODO；所有程式步驟皆完整程式碼 ✅

**3. Type consistency：**
- `ToolSpec(name, description, parameters)`、`ToolCall(name, arguments)`、`ToolResult(call, output)`、`ToolTurn(text, tool_calls)` 在 Task 1 定義，Task 2/3/4 一致使用 ✅
- `generate_tool_turn(*, system_prompt, messages, tools, tool_results) -> ToolTurn` 在 Protocol（Task 2）、FakeLLM（Task 2 測試）、GeminiClient（Task 4）一致 ✅
- `ToolRegistry.register/specs/dispatch`、`CareAgent(..., tools=, max_tool_iters=)`、`build_weather_handler(fetch_json=)`、`WEATHER_SPEC.name=="get_weather"` 前後一致 ✅
- 既有 `test_agent.py` 三測試以 `CareAgent(llm, memory, context)`（`tools=None`）走 `generate`、行為不變 ✅
