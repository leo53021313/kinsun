from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.knowledge.store import SqliteFactStore


def _fact(content, sid="u1", cat=FactCategory.CONDITION, prov=Provenance.SELF_CLAIMED):
    return Fact(sid, cat, content, prov, 0.6)


def test_add_then_all_for():
    store = SqliteFactStore(":memory:")
    store.add(_fact("高血壓"))
    facts = store.all_for("u1")
    assert len(facts) == 1
    assert facts[0].content == "高血壓"
    assert facts[0].provenance == Provenance.SELF_CLAIMED


def test_dedupe_same_fact():
    store = SqliteFactStore(":memory:")
    store.add(_fact("高血壓"))
    store.add(_fact("高血壓"))
    assert len(store.all_for("u1")) == 1


def test_sessions_isolated():
    store = SqliteFactStore(":memory:")
    store.add(_fact("高血壓", sid="u1"))
    store.add(_fact("糖尿病", sid="u2"))
    assert [f.content for f in store.all_for("u1")] == ["高血壓"]


def test_empty_session():
    assert SqliteFactStore(":memory:").all_for("nobody") == []
