"""MedicationFacts 用藥事實提供者測試。"""

from datetime import datetime, timedelta, timezone

from kinsun.accounts.models import Elder
from kinsun.accounts.service import AccountService
from kinsun.medications.facts import MedicationFacts
from kinsun.medications.models import MedicationSlot
from kinsun.medications.service import MedicationService
from tests.fakes import FakeAccountRepository, FakeMedicationStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def _facts(*, meds):
    repo = FakeAccountRepository()
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    accounts = AccountService(repo, clock=lambda: NOW)
    medications = MedicationService(FakeMedicationStore(), new_id=lambda: "m1")
    for name, slots in meds:
        medications.add("e1", name, slots)
    return MedicationFacts(accounts, medications)


def test_facts_lists_current_meds():
    facts = _facts(meds=[("降血壓藥", (MedicationSlot.MORNING, MedicationSlot.EVENING))])
    out = facts.facts("U-elder")
    assert "降血壓藥" in out
    assert "早上、晚上" in out


def test_facts_empty_when_unknown_line():
    facts = _facts(meds=[("鈣片", (MedicationSlot.BEDTIME,))])
    assert facts.facts("U-stranger") == ""


def test_facts_empty_when_no_meds():
    repo = FakeAccountRepository()
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    accounts = AccountService(repo, clock=lambda: NOW)
    facts = MedicationFacts(accounts, MedicationService(FakeMedicationStore()))
    assert facts.facts("U-elder") == ""
