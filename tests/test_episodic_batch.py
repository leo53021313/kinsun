from kinsun.episodic.batch import run_episode_extraction
from kinsun.episodic.embeddings import EmbeddingError
from kinsun.episodic.store import SqliteVectorStore
from kinsun.llm import Message


class StubShortTerm:
    def __init__(self, messages):
        self._messages = messages

    def recent(self, session_id):
        return self._messages


class StubExtractor:
    def __init__(self, episodes):
        self._episodes = episodes

    def extract(self, messages):
        return self._episodes


class FlakyEmbedder:
    def embed(self, text):
        if text == "壞":
            raise EmbeddingError("boom")
        return [1.0, 0.0]


def test_run_stores_and_skips_failed_embed():
    store = SqliteVectorStore(":memory:")
    n = run_episode_extraction(
        "u1",
        short_term=StubShortTerm([Message("user", "嗨")]),
        extractor=StubExtractor(["好的", "壞"]),
        embedder=FlakyEmbedder(),
        store=store,
    )
    assert n == 1
    assert store.search("u1", [1.0, 0.0], k=10) == ["好的"]
