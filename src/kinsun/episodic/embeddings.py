"""Gemini 文字 embeddings。"""

from __future__ import annotations

from typing import Protocol


class EmbeddingError(Exception):
    """embedding 產生失敗。"""


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class GeminiEmbedder:
    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise EmbeddingError("缺少 GEMINI_API_KEY")
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def embed(self, text: str) -> list[float]:
        try:
            result = self._client.models.embed_content(model=self._model, contents=text)
            return list(result.embeddings[0].values)
        except Exception as exc:  # noqa: BLE001 - 統一轉成可辨識的 EmbeddingError
            raise EmbeddingError(f"Gemini embedding 失敗：{exc}") from exc
