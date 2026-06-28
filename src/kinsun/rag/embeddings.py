"""Embedding 介面與輕量測試實作。"""

from __future__ import annotations

from typing import Protocol


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class CharacterHashEmbedding:
    """不依賴外部模型的測試 embedding。

    這不是 production 向量模型，只用來讓 vector store 介面可測。
    """

    def __init__(self, dimensions: int = 32) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions 必須大於 0")
        self._dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self._dimensions
        for char in text:
            vector[ord(char) % self._dimensions] += 1.0
        length = sum(value * value for value in vector) ** 0.5
        if length == 0:
            return tuple(vector)
        return tuple(value / length for value in vector)
