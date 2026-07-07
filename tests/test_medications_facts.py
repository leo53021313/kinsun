"""MedicationFacts 用藥事實提供者測試。"""

from kinsun.medications.facts import MedicationFacts
from kinsun.medications.models import MedicationSlot
from kinsun.medications.service import MedicationService
from tests.fakes import FakeMedicationStore


def _facts(*, meds):
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: "m1")
    for name, slots in meds:
        medications.save("e1", name, slots)
    return MedicationFacts(medications)


def test_facts_lists_current_meds():
    facts = _facts(meds=[("降血壓藥", (MedicationSlot.MORNING, MedicationSlot.EVENING))])
    section = facts.facts("e1")
    assert section.items == ["降血壓藥（早上、晚上）"]
    assert "固定服用的藥" in section.title


def test_facts_none_when_unknown_elder():
    facts = _facts(meds=[("鈣片", (MedicationSlot.BEDTIME,))])
    assert facts.facts("e-stranger") is None


def test_facts_none_when_no_meds():
    facts = MedicationFacts(MedicationService(FakeMedicationStore()))
    assert facts.facts("e1") is None
