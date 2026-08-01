"""Embedding 介面與輕量測試實作。"""

from __future__ import annotations

import json
import time
from typing import Protocol

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from kinsun import tracing
from kinsun.llm import is_retryable_llm_error
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

    # 輸出維持關閉：回傳的是 768 維向量，攤進 span 只是把畫面塞爆。
    @tracing.track(name="embedding", type="general", capture_input=True, capture_output=False)
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

        def _call():
            # 每次呼叫前的節流（含首次）：這是配額節流，不是重試退避，故留在被重試的
            # 函式內；重試間的退避由 tenacity 的 wait 負責，兩者共用注入的 self._sleep。
            if self._request_delay_seconds:
                self._sleep(self._request_delay_seconds)
            return self._client.models.embed_content(
                model=self._model,
                contents=texts[0] if len(texts) == 1 else list(texts),
                config=config,
            )

        # 指數退避 initial*2**n（上限 max）與原 _retry_delay 等價；只重試可重試錯誤
        # （429／quota／逾時），其餘立即拋出。sleep 走注入的 self._sleep 讓測試可斷言。
        retrying = Retrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(
                multiplier=self._retry_initial_delay_seconds,
                exp_base=2,
                max=self._retry_max_delay_seconds,
            ),
            retry=retry_if_exception(_is_retryable_embedding_error),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            response = retrying(_call)
        except Exception as exc:  # noqa: BLE001 - 統一翻成可辨識錯誤
            raise EmbeddingError(f"Gemini embedding 失敗：{exc}") from exc
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
    """沿用全庫共用的判準（2026-07-27 搬進 `llm.py`）。

    保留這層薄包裝而不是直接用：本模組的 `Retrying` 已指名它，改呼叫端等於動一段
    有回歸測試守住的重試設定，收益為零。判準本身只有一份。
    """
    return is_retryable_llm_error(exc)


class LocalEmbeddingModel:
    """地端嵌入服務（services/embedding，BGE-M3）的呼叫端。

    2026-08-01 A/B 換掉 Gemini 的理由：一般長輩口語 R@1 82.0%／MRR 0.900（Gemini
    78.7%／0.885）、全站 5,667 篇建置約 2 分鐘（Gemini 約 2.9 小時且每日配額只夠
    三分之一）。台語詞彙 Gemini 較強（95.2% vs 85.7%，21 題差 2 題），由
    `retriever._SYNONYMS` 的同義詞展開補回（實測 R@3 90.5% → 95.2%）。
    """

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        dimensions: int = RAG_EMBEDDING_DIMENSIONS,
        api_key: str = "",
        request_timeout_seconds: float = 60.0,
        batch_size: int = _DEFAULT_EMBEDDING_BATCH_SIZE,
        transport=None,
    ) -> None:
        if not endpoint:
            raise EmbeddingError("缺少 RAG_EMBEDDING_ENDPOINT")
        if dimensions <= 0:
            raise EmbeddingError("embedding dimensions 必須大於 0")
        if request_timeout_seconds <= 0:
            raise EmbeddingError("embedding request timeout 必須大於 0")
        if batch_size <= 0:
            raise EmbeddingError("embedding batch size 必須大於 0")
        self._endpoint = endpoint
        self._model = model
        self._dimensions = dimensions
        self._api_key = api_key
        self._timeout = request_timeout_seconds
        self._batch_size = batch_size
        if transport is None:
            from kinsun.transport import HttpxTransport

            transport = HttpxTransport()
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        return self.embed_document(text)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed_batch((text,))[0]

    def embed_document(self, text: str, *, title: str | None = None) -> tuple[float, ...]:
        return self.embed_documents((text,), title=title)[0]

    def embed_documents(
        self,
        texts: tuple[str, ...],
        *,
        title: str | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        # 文件一律帶標題：2026-08-01 A/B 實測含標題 R@1 98.4%、純內文 85.2%。
        prefix = f"{title}\n" if title else ""
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = tuple(prefix + text for text in texts[start : start + self._batch_size])
            vectors.extend(self._embed_batch(batch))
        return tuple(vectors)

    def _embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        for text in texts:
            if not text.strip():
                raise EmbeddingError("embedding 輸入不可為空字串")
        headers = {"Content-Type": "application/json"}
        if self._api_key:  # 共用金鑰；未設＝內網開發模式（比照 ASR／TTS）
            headers["X-Api-Key"] = self._api_key
        from kinsun.transport import TransportError, read_json

        try:
            response = self._transport.request(
                "POST",
                self._endpoint,
                data=json.dumps({"texts": list(texts)}).encode("utf-8"),
                headers=headers,
                timeout=self._timeout,
            )
            payload = read_json(response)
        except TransportError as exc:
            raise EmbeddingError(f"地端嵌入服務呼叫失敗：{exc}") from exc
        vectors = payload.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("地端嵌入服務回應的向量數與請求段數不符")
        for vector in vectors:
            # 維度不符若放行，會炸在 pgvector 的 SQL 層，錯誤訊息離根因很遠；
            # 在這裡擋下來才看得出是「換了模型但 schema 沒跟著改」。
            if len(vector) != self._dimensions:
                raise EmbeddingError(
                    f"地端嵌入服務的 embedding 維度不符："
                    f"預期 {self._dimensions}，實際 {len(vector)}"
                )
        return tuple(tuple(float(value) for value in vector) for vector in vectors)


def build_embedding_model(
    *,
    backend: str,
    model: str,
    dimensions: int = RAG_EMBEDDING_DIMENSIONS,
    request_timeout_seconds: float = 60.0,
    batch_size: int = _DEFAULT_EMBEDDING_BATCH_SIZE,
    endpoint: str = "",
    local_api_key: str = "",
    transport=None,
    gemini_api_key: str = "",
    gemini_client=None,
    **gemini_options,
) -> QueryEmbeddingModel:
    """依 `RAG_EMBEDDING_BACKEND` 決定用地端服務或雲端 Gemini。

    命名比照 ASR／TTS 的 `*_BACKEND` 慣例；地端只需 endpoint，配額相關的重試與
    節流參數（`gemini_options`）僅對雲端有意義。
    """
    if backend == "local":
        return LocalEmbeddingModel(
            endpoint=endpoint,
            model=model,
            dimensions=dimensions,
            api_key=local_api_key,
            request_timeout_seconds=request_timeout_seconds,
            batch_size=batch_size,
            transport=transport,
        )
    if backend != "gemini":
        raise EmbeddingError(f"RAG_EMBEDDING_BACKEND 只支援 gemini 或 local，收到：{backend}")
    return GeminiEmbeddingModel(
        api_key=gemini_api_key,
        model=model,
        dimensions=dimensions,
        request_timeout_seconds=request_timeout_seconds,
        batch_size=batch_size,
        client=gemini_client,
        **gemini_options,
    )


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
