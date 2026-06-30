from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.accounts.models import Elder
from kinsun.accounts.service import AccountService
from kinsun.appointment.facts import AppointmentFacts
from kinsun.appointment.service import AppointmentService
from tests.fakes import FakeAccountRepository, FakeAppointmentStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, 9, 0, tzinfo=TPE)


def _facts(appts):
    repo = FakeAccountRepository()
    repo.save_elder(Elder("e1", "阿公", "U-elder"))
    accounts = AccountService(repo, clock=lambda: NOW, new_id=lambda: "x", new_code=lambda: "c")
    aids = (f"a{i}" for i in count(1))
    appointments = AppointmentService(FakeAppointmentStore(), new_id=lambda: next(aids))
    for date, label in appts:
        appointments.add("e1", date, label)
    return AppointmentFacts(accounts, appointments, clock=lambda: NOW)


def test_injects_upcoming_sorted():
    facts = _facts([("2026-07-20", "心臟科回診"), ("2026-07-12", "眼科回診")])
    out = facts.facts("U-elder")
    assert "即將到來的回診" in out
    assert out.index("2026-07-12") < out.index("2026-07-20")
    assert "眼科回診" in out and "心臟科回診" in out


def test_empty_when_no_upcoming():
    facts = _facts([("2026-07-01", "過去")])  # 早於 NOW(07-10)
    assert facts.facts("U-elder") == ""


def test_empty_when_elder_unknown():
    facts = _facts([("2026-07-20", "x")])
    assert facts.facts("U-stranger") == ""
