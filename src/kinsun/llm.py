"""LLM 介面與 Gemini 實作。系統指令＋多輪訊息 → 繁體國語漢字回應。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """LLM 呼叫失敗。"""


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    # 模型回傳 function_call 時附帶的思考簽章；gemini-3 thinking 模型要求原封回帶。
    thought_signature: bytes | None = None


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
    return [
        {"role": role_map.get(m.role, "user"), "parts": [{"text": m.content}]} for m in messages
    ]


def _extract_tool_calls(response) -> list[ToolCall]:
    """逐一取出回應 parts 的 function_call，並保留同 part 的 thought_signature。

    需走 parts（而非 response.function_calls），因為 thought_signature 掛在 part 上，
    是 gemini-3 thinking 模型後續回帶工具結果時的必要欄位。
    """
    candidates = response.candidates or []
    if not candidates or candidates[0].content is None:
        return []
    calls: list[ToolCall] = []
    for part in candidates[0].content.parts or []:
        fc = part.function_call
        if fc is None:
            continue
        calls.append(
            ToolCall(
                name=fc.name,
                arguments=dict(fc.args or {}),
                thought_signature=part.thought_signature,
            )
        )
    return calls


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
            # 回帶模型原始 function_call part（含 thought_signature）：gemini-3 thinking 模型
            # 要求 functionCall part 保留 thought_signature，缺了會 400 INVALID_ARGUMENT。
            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=tr.call.name, args=tr.call.arguments
                            ),
                            thought_signature=tr.call.thought_signature,
                        )
                    ],
                )
            )
            contents.append(
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name=tr.call.name, response={"result": tr.output}
                        )
                    ],
                )
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
        tool_calls = _extract_tool_calls(response)
        if tool_calls:
            return ToolTurn(text=None, tool_calls=tool_calls)
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return ToolTurn(text=text, tool_calls=[])


def build_gemini_for(settings, model: str) -> GeminiClient:
    """按用途建 Gemini client（✅ D-16 丁-5）：模型同主設定時呼叫端應直接共用主 client。"""
    return GeminiClient(
        api_key=settings.gemini_api_key, model=model, timeout=settings.gemini_timeout_seconds
    )
