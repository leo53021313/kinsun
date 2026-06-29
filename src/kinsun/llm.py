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
