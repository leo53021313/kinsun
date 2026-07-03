import pytest

from kinsun.rag.embeddings import EmbeddingError, GeminiEmbeddingModel


class _FakeEmbedding:
    values = [0.1, 0.2, 0.3]


class _FakeResponse:
    embeddings = [_FakeEmbedding()]


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
        return _FakeResponse()


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
