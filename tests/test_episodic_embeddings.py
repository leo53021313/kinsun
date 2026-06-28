import pytest

from kinsun.episodic.embeddings import Embedder, EmbeddingError, GeminiEmbedder


def test_empty_api_key_raises():
    with pytest.raises(EmbeddingError):
        GeminiEmbedder(api_key="", model="gemini-embedding-001")


def test_fake_satisfies_protocol():
    class FakeEmbedder:
        def embed(self, text: str) -> list[float]:
            return [0.1, 0.2]

    client: Embedder = FakeEmbedder()
    assert client.embed("x") == [0.1, 0.2]
