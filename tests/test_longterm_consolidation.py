from kinsun.episodic.embeddings import EmbeddingError
from kinsun.episodic.store import SqliteVectorStore
from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.knowledge.store import SqliteFactStore
from kinsun.llm import Message
from kinsun.longterm.consolidation import run_consolidation
from kinsun.longterm.extractor import Consolidation


class StubShortTerm:
    def __init__(self, messages):
        self._messages = messages

    def recent(self, session_id):
        return self._messages


class StubExtractor:
    def __init__(self, consolidation):
        self._c = consolidation

    def extract(self, session_id, messages):
        return self._c


class FlakyEmbedder:
    def embed(self, text):
        if text == "壞":
            raise EmbeddingError("boom")
        return [1.0, 0.0]


def test_routes_facts_and_episodes():
    fact_store = SqliteFactStore(":memory:")
    vector_store = SqliteVectorStore(":memory:")
    consolidation = Consolidation(
        facts=[Fact("u1", FactCategory.CONDITION, "高血壓", Provenance.SELF_CLAIMED, 0.6)],
        episodes=["好的", "壞"],
    )
    result = run_consolidation(
        "u1",
        short_term=StubShortTerm([Message("user", "嗨")]),
        extractor=StubExtractor(consolidation),
        embedder=FlakyEmbedder(),
        fact_store=fact_store,
        vector_store=vector_store,
    )
    assert result.facts_stored == 1
    assert result.episodes_stored == 1
    assert [f.content for f in fact_store.all_for("u1")] == ["高血壓"]
    assert vector_store.search("u1", [1.0, 0.0], k=10) == ["好的"]
