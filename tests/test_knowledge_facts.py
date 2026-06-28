from kinsun.knowledge.facts import Fact, FactCategory, Provenance


def test_enum_values():
    assert FactCategory.MEDICATION.value == "medication"
    assert Provenance.SELF_CLAIMED.value == "self_claimed"


def test_fact_construction():
    f = Fact("u1", FactCategory.CONDITION, "高血壓", Provenance.SELF_CLAIMED, 0.6)
    assert f.session_id == "u1"
    assert f.category == FactCategory.CONDITION
    assert f.provenance == Provenance.SELF_CLAIMED
