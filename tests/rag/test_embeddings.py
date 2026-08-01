import pytest

from kinsun.rag.embeddings import EmbeddingError, GeminiEmbeddingModel


class _FakeEmbedding:
    values = [0.1, 0.2, 0.3]


class _FakeResponse:
    def __init__(self, count=1):
        self.embeddings = [_FakeEmbedding() for _ in range(count)]


class _FakeModels:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.calls = []
        self.failures = failures or []

    def embed_content(self, *, model, contents, config):
        self.calls.append(
            (model, contents, config.task_type, config.output_dimensionality, config.title)
        )
        if self.failures:
            raise self.failures.pop(0)
        return _FakeResponse(len(contents) if isinstance(contents, list) else 1)


class _FakeClient:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.models = _FakeModels(failures)


def test_gemini_embedding_uses_query_and_document_task_types():
    client = _FakeClient()
    model = GeminiEmbeddingModel(
        api_key="",
        model="gemini-embedding-001",
        dimensions=3,
        client=client,
    )

    assert model.embed_query("三高") == (0.1, 0.2, 0.3)
    assert model.embed_document("高血壓衛教", title="高血壓") == (0.1, 0.2, 0.3)
    assert client.models.calls == [
        ("gemini-embedding-001", "三高", "QUESTION_ANSWERING", 3, None),
        ("gemini-embedding-001", "高血壓衛教", "RETRIEVAL_DOCUMENT", 3, "高血壓"),
    ]


def test_gemini_embedding_rejects_empty_text():
    model = GeminiEmbeddingModel(api_key="", model="m", dimensions=3, client=_FakeClient())
    with pytest.raises(EmbeddingError):
        model.embed_query(" ")


def test_gemini_embedding_batches_document_chunks():
    client = _FakeClient()
    model = GeminiEmbeddingModel(
        api_key="",
        model="gemini-embedding-001",
        dimensions=3,
        client=client,
    )

    vectors = model.embed_documents(("第一段", "第二段"), title="高血壓")

    assert vectors == ((0.1, 0.2, 0.3), (0.1, 0.2, 0.3))
    assert client.models.calls == [
        (
            "gemini-embedding-001",
            ["第一段", "第二段"],
            "RETRIEVAL_DOCUMENT",
            3,
            "高血壓",
        )
    ]


def test_gemini_embedding_respects_configured_batch_size():
    client = _FakeClient()
    model = GeminiEmbeddingModel(
        api_key="",
        model="gemini-embedding-001",
        dimensions=3,
        batch_size=1,
        client=client,
    )

    assert len(model.embed_documents(("第一段", "第二段"))) == 2
    assert [call[1] for call in client.models.calls] == ["第一段", "第二段"]


def test_gemini_embedding_rejects_invalid_timeout_and_batch_size():
    with pytest.raises(EmbeddingError, match="timeout"):
        GeminiEmbeddingModel(
            api_key="",
            model="gemini-embedding-001",
            request_timeout_seconds=0,
            client=_FakeClient(),
        )
    with pytest.raises(EmbeddingError, match="batch size"):
        GeminiEmbeddingModel(
            api_key="",
            model="gemini-embedding-001",
            batch_size=0,
            client=_FakeClient(),
        )


def test_gemini_embedding_retries_429_with_backoff():
    sleeps = []
    client = _FakeClient(failures=[RuntimeError("429 Resource exhausted")])
    model = GeminiEmbeddingModel(
        api_key="",
        model="gemini-embedding-001",
        dimensions=3,
        request_delay_seconds=0.5,
        max_retries=2,
        retry_initial_delay_seconds=3,
        retry_max_delay_seconds=10,
        client=client,
        sleeper=sleeps.append,
    )

    assert model.embed_document("高血壓衛教") == (0.1, 0.2, 0.3)
    assert len(client.models.calls) == 2
    assert sleeps == [0.5, 3, 0.5]


def test_gemini_embedding_does_not_retry_non_retryable_error():
    sleeps = []
    client = _FakeClient(failures=[RuntimeError("bad request")])
    model = GeminiEmbeddingModel(
        api_key="",
        model="gemini-embedding-001",
        dimensions=3,
        max_retries=2,
        client=client,
        sleeper=sleeps.append,
    )

    with pytest.raises(EmbeddingError, match="bad request"):
        model.embed_document("高血壓衛教")
    assert len(client.models.calls) == 1
    assert sleeps == []


class _FakeTransport:
    """記錄請求並回固定向量的假傳輸；長度依請求段數決定。"""

    def __init__(self, dimensions: int = 4, failures: list[Exception] | None = None) -> None:
        self.calls: list[dict] = []
        self._dimensions = dimensions
        self._failures = failures or []

    def request(self, method, url, *, data=None, headers=None, timeout):
        import json as _json

        from kinsun.transport import Response

        if self._failures:
            raise self._failures.pop(0)
        payload = _json.loads(data)
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "texts": payload["texts"],
            }
        )
        vectors = [[0.5] * self._dimensions for _ in payload["texts"]]
        body = _json.dumps(
            {"vectors": vectors, "model": "BAAI/bge-m3", "dimensions": self._dimensions}
        ).encode("utf-8")
        return Response(status=200, headers={}, body=body)


def _local_model(transport, **overrides):
    from kinsun.rag.embeddings import LocalEmbeddingModel

    kwargs = {
        "endpoint": "http://127.0.0.1:8003/embed",
        "model": "BAAI/bge-m3",
        "dimensions": 4,
        "transport": transport,
    }
    kwargs.update(overrides)
    return LocalEmbeddingModel(**kwargs)


def test_local_embedding_posts_texts_and_returns_vectors():
    transport = _FakeTransport()

    model = _local_model(transport)
    vector = model.embed_query("高血壓要注意什麼")

    assert len(vector) == 4
    assert transport.calls[0]["method"] == "POST"
    assert transport.calls[0]["texts"] == ["高血壓要注意什麼"]
    assert model.model_name == "BAAI/bge-m3"
    assert model.dimensions == 4


def test_local_embedding_prepends_title_to_document():
    """文件要帶標題。

    2026-08-01 A/B 實測：含標題 R@1 98.4%、純內文 85.2%。這是同一個模型、同一份
    語料下的差距，不是可有可無的調校。查詢端則不加標題（沒有標題可加）。
    """
    transport = _FakeTransport()

    model = _local_model(transport)
    model.embed_document("正常喝水並不會增加體重。", title="連喝水也會胖")

    assert transport.calls[0]["texts"] == ["連喝水也會胖\n正常喝水並不會增加體重。"]


def test_local_embedding_batches_documents_within_batch_size():
    transport = _FakeTransport()

    model = _local_model(transport, batch_size=2)
    vectors = model.embed_documents(("甲", "乙", "丙"), title="標題")

    assert len(vectors) == 3
    assert [call["texts"] for call in transport.calls] == [
        ["標題\n甲", "標題\n乙"],
        ["標題\n丙"],
    ]


def test_local_embedding_sends_api_key_when_configured():
    transport = _FakeTransport()

    _local_model(transport, api_key="s3cret").embed_query("測試")

    assert transport.calls[0]["headers"]["X-Api-Key"] == "s3cret"


def test_local_embedding_omits_api_key_header_when_unset():
    transport = _FakeTransport()

    _local_model(transport).embed_query("測試")

    assert "X-Api-Key" not in transport.calls[0]["headers"]


def test_local_embedding_rejects_dimension_mismatch():
    """服務回傳的維度與設定不符時要當場失敗。

    維度不一致寫進 pgvector 會直接炸在 SQL 層，錯誤訊息離根因很遠；
    在呼叫端擋下來才看得出是「模型換了但 schema 沒改」。
    """
    from kinsun.rag.embeddings import EmbeddingError

    transport = _FakeTransport(dimensions=1024)

    with pytest.raises(EmbeddingError, match="維度"):
        _local_model(transport, dimensions=768).embed_query("測試")


def test_local_embedding_wraps_transport_failure():
    from kinsun.rag.embeddings import EmbeddingError
    from kinsun.transport import TransportError

    transport = _FakeTransport(failures=[TransportError("connection refused")])

    with pytest.raises(EmbeddingError, match="地端嵌入服務"):
        _local_model(transport).embed_query("測試")


def test_local_embedding_rejects_empty_text():
    from kinsun.rag.embeddings import EmbeddingError

    with pytest.raises(EmbeddingError):
        _local_model(_FakeTransport()).embed_query("   ")


def test_build_embedding_model_defaults_to_gemini():
    from kinsun.rag.embeddings import GeminiEmbeddingModel, build_embedding_model

    model = build_embedding_model(
        backend="gemini",
        model="gemini-embedding-001",
        gemini_api_key="k",
        gemini_client=_FakeClient(),
    )

    assert isinstance(model, GeminiEmbeddingModel)
    assert model.model_name == "gemini-embedding-001"


def test_build_embedding_model_returns_local_client_when_backend_is_local():
    from kinsun.rag.embeddings import LocalEmbeddingModel, build_embedding_model

    model = build_embedding_model(
        backend="local",
        model="BAAI/bge-m3",
        dimensions=1024,
        endpoint="http://127.0.0.1:8003/embed",
        transport=_FakeTransport(dimensions=1024),
    )

    assert isinstance(model, LocalEmbeddingModel)
    assert model.dimensions == 1024


def test_build_embedding_model_requires_endpoint_for_local_backend():
    from kinsun.rag.embeddings import EmbeddingError, build_embedding_model

    with pytest.raises(EmbeddingError, match="RAG_EMBEDDING_ENDPOINT"):
        build_embedding_model(backend="local", model="BAAI/bge-m3")


def test_build_embedding_model_rejects_unknown_backend():
    from kinsun.rag.embeddings import EmbeddingError, build_embedding_model

    with pytest.raises(EmbeddingError, match="RAG_EMBEDDING_BACKEND"):
        build_embedding_model(backend="openai", model="x")
