from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.knowledge.recall import KnowledgeRecaller, format_facts_for_prompt


def test_format_empty_returns_blank():
    assert format_facts_for_prompt([]) == ""


def test_format_includes_provenance_label():
    facts = [Fact("u1", FactCategory.CONDITION, "高血壓", Provenance.SELF_CLAIMED, 0.6)]
    out = format_facts_for_prompt(facts)
    assert "高血壓" in out
    assert "長者自述" in out
    assert "慢性病" in out


class _Store:
    def __init__(self, facts):
        self._facts = facts

    def all_for(self, session_id):
        return self._facts


def test_recaller_returns_blank_for_no_facts():
    assert KnowledgeRecaller(_Store([])).recall("u1") == ""


class _BoomStore:
    def all_for(self, session_id):
        raise RuntimeError("db down")


def test_recaller_failsafe_on_error():
    assert KnowledgeRecaller(_BoomStore()).recall("u1") == ""
