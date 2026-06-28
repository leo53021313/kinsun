"""LLM 介面與 Gemini 實作。系統指令＋使用者文字 → 繁體國語漢字回應。"""

from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """LLM 呼叫失敗。"""


class LLMClient(Protocol):
    def generate(self, *, system_prompt: str, user_text: str) -> str: ...


class GeminiClient:
    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise LLMError("缺少 GEMINI_API_KEY")
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    def generate(self, *, system_prompt: str, user_text: str) -> str:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_text,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 LLMError
            raise LLMError(f"Gemini 呼叫失敗：{exc}") from exc
        text = response.text
        if not text:
            raise LLMError("Gemini 回應為空")
        return text
