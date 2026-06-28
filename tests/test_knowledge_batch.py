from kinsun.knowledge.batch import run_fact_extraction
from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.knowledge.store import SqliteFactStore
from kinsun.llm import Message


class StubShortTerm:
    def __init__(self, messages):
        self._messages = messages

    def recent(self, session_id):
        return self._messages


class StubExtractor:
    def __init__(self, facts):
        self._facts = facts

    def extract(self, session_id, messages):
        return self._facts


def test_run_fact_extraction_stores_and_counts():
    store = SqliteFactStore(":memory:")
    facts = [Fact("u1", FactCategory.CONDITION, "高血壓", Provenance.SELF_CLAIMED, 0.6)]
    n = run_fact_extraction(
        "u1",
        short_term=StubShortTerm([Message("user", "我有高血壓")]),
        extractor=StubExtractor(facts),
        store=store,
    )
    assert n == 1
    assert [f.content for f in store.all_for("u1")] == ["高血壓"]
