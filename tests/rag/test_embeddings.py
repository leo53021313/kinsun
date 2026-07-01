import pytest

from kinsun.rag.embeddings import EmbeddingError, GeminiEmbeddingModel


class _FakeEmbedding:
    values = [0.1, 0.2, 0.3]


class _FakeResponse:
    embeddings = [_FakeEmbedding()]


class _FakeModels:
    def __init__(self) -> None:
        self.calls = []

    def embed_content(self, *, model, contents, config):
        self.calls.append(
            (model, contents, config.task_type, config.output_dimensionality, config.title)
        )
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.models = _FakeModels()


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
