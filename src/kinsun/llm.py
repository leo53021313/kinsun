"""LLM 介面與 Gemini 實作。系統指令＋多輪訊息 → 繁體國語漢字回應。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """LLM 呼叫失敗。"""


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant"
    text: str


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


def _to_contents(messages: list[Message]) -> list[dict]:
    role_map = {"user": "user", "assistant": "model"}
    return [{"role": role_map.get(m.role, "user"), "parts": [{"text": m.text}]} for m in messages]


class GeminiClient:
    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise LLMError("缺少 GEMINI_API_KEY")
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=_to_contents(messages),
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 LLMError
            raise LLMError(f"Gemini 呼叫失敗：{exc}") from exc
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return text

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
                        {
                            "function_response": {
                                "name": tr.call.name,
                                "response": {"result": tr.output},
                            }
                        }
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
