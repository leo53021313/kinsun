"""Embedding 介面與輕量測試實作。"""

from __future__ import annotations

import time
from typing import Protocol

from kinsun.rag.schemas import RAG_EMBEDDING_DIMENSIONS

_GEMINI_EMBEDDING_001 = "gemini-embedding-001"
_DEFAULT_EMBEDDING_BATCH_SIZE = 20


class EmbeddingError(Exception):
    """Embedding 產生失敗。"""


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class QueryEmbeddingModel(EmbeddingModel, Protocol):
    @property
    def model_name(self) -> str: ...
    @property
    def dimensions(self) -> int: ...
    def embed_query(self, text: str) -> tuple[float, ...]: ...
    def embed_document(self, text: str, *, title: str | None = None) -> tuple[float, ...]: ...


class GeminiEmbeddingModel:
    """Gemini embedding adapter。

    RAG 以 768 維向量落 pgvector，避免高維度索引在 pgvector 上不可建 HNSW。
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int = RAG_EMBEDDING_DIMENSIONS,
        request_delay_seconds: float = 0.0,
        max_retries: int = 0,
        retry_initial_delay_seconds: float = 30.0,
        retry_max_delay_seconds: float = 300.0,
        request_timeout_seconds: float = 60.0,
        batch_size: int = _DEFAULT_EMBEDDING_BATCH_SIZE,
        client=None,
        sleeper=time.sleep,
    ) -> None:
        if not api_key and client is None:
            raise EmbeddingError("缺少 GEMINI_API_KEY")
        if dimensions <= 0:
            raise EmbeddingError("embedding dimensions 必須大於 0")
        if request_delay_seconds < 0:
            raise EmbeddingError("embedding request delay 不可小於 0")
        if max_retries < 0:
            raise EmbeddingError("embedding max retries 不可小於 0")
        if retry_initial_delay_seconds < 0 or retry_max_delay_seconds < 0:
            raise EmbeddingError("embedding retry delay 不可小於 0")
        if request_timeout_seconds <= 0:
            raise EmbeddingError("embedding request timeout 必須大於 0")
        if batch_size <= 0:
            raise EmbeddingError("embedding batch size 必須大於 0")
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(request_timeout_seconds * 1000)),
            )
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._request_delay_seconds = request_delay_seconds
        self._max_retries = max_retries
        self._retry_initial_delay_seconds = retry_initial_delay_seconds
        self._retry_max_delay_seconds = retry_max_delay_seconds
        self._batch_size = batch_size
        self._sleep = sleeper

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        return self.embed_document(text)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text, task_type="QUESTION_ANSWERING")

    def embed_document(self, text: str, *, title: str | None = None) -> tuple[float, ...]:
        return self._embed(text, task_type="RETRIEVAL_DOCUMENT", title=title)

    def embed_documents(
        self,
        texts: tuple[str, ...],
        *,
        title: str | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """批次產生同一文件的 chunk embeddings；舊模型以逐筆呼叫維持語意。"""
        if not texts:
            return ()
        if self._model.rsplit("/", 1)[-1] != _GEMINI_EMBEDDING_001:
            return tuple(
                self._embed(text, task_type="RETRIEVAL_DOCUMENT", title=title) for text in texts
            )
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(
                self._embed_many(
                    texts[start : start + self._batch_size],
                    task_type="RETRIEVAL_DOCUMENT",
                    title=title,
                )
            )
        return tuple(vectors)

    def _embed(self, text: str, *, task_type: str, title: str | None = None) -> tuple[float, ...]:
        return self._embed_many((text,), task_type=task_type, title=title)[0]

    def _embed_many(
        self,
        texts: tuple[str, ...],
        *,
        task_type: str,
        title: str | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("不可對空白文字產生 embedding")
        from google.genai import types

        config = types.EmbedContentConfig(
            task_type=task_type,
            title=title,
            output_dimensionality=self._dimensions,
        )
        attempt = 0
        while True:
            if self._request_delay_seconds:
                self._sleep(self._request_delay_seconds)
            try:
                response = self._client.models.embed_content(
                    model=self._model,
                    contents=texts[0] if len(texts) == 1 else list(texts),
                    config=config,
                )
                break
            except Exception as exc:  # noqa: BLE001 - 統一翻成可辨識錯誤
                if attempt >= self._max_retries or not _is_retryable_embedding_error(exc):
                    raise EmbeddingError(f"Gemini embedding 失敗：{exc}") from exc
                self._sleep(
                    _retry_delay(
                        attempt,
                        self._retry_initial_delay_seconds,
                        self._retry_max_delay_seconds,
                    )
                )
                attempt += 1
        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Gemini embedding 數量不符：預期 {len(texts)}，實際 {len(embeddings)}"
            )
        if any(not embedding.values for embedding in embeddings):
            raise EmbeddingError("Gemini embedding 回應為空")
        vectors = tuple(
            tuple(float(value) for value in embedding.values) for embedding in embeddings
        )
        invalid = next((len(vector) for vector in vectors if len(vector) != self._dimensions), None)
        if invalid is not None:
            raise EmbeddingError(f"embedding 維度不符：預期 {self._dimensions}，實際 {invalid}")
        return vectors


def _is_retryable_embedding_error(exc: Exception) -> bool:
    message = str(exc).lower()
    retryable_markers = (
        "429",
        "rate limit",
        "too many requests",
        "resource_exhausted",
        "quota",
        "temporarily unavailable",
        "503",
        "timed out",
        "timeout",
        "readtimeout",
        "connecttimeout",
    )
    return any(marker in message for marker in retryable_markers)


def _retry_delay(attempt: int, initial_delay: float, max_delay: float) -> float:
    if initial_delay == 0:
        return 0.0
    return min(max_delay, initial_delay * (2**attempt))


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

    @property
    def model_name(self) -> str:
        return "character-hash-test"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self.embed(text)

    def embed_document(self, text: str, *, title: str | None = None) -> tuple[float, ...]:
        prefix = f"{title}\n" if title else ""
        return self.embed(prefix + text)
