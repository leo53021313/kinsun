from datetime import datetime, timedelta, timezone
from itertools import count

from kinsun.appointments.facts import AppointmentFacts
from kinsun.appointments.service import AppointmentService
from tests.fakes import FakeAppointmentStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 10, 9, 0, tzinfo=TPE)


def _facts(appts):
    aids = (f"a{i}" for i in count(1))
    appointments = AppointmentService(FakeAppointmentStore(), new_id=lambda: next(aids))
    for date, label in appts:
        appointments.save("e1", date, label)
    return AppointmentFacts(appointments, clock=lambda: NOW)


def test_injects_upcoming_sorted():
    facts = _facts([("2026-07-20", "心臟科回診"), ("2026-07-12", "眼科回診")])
    section = facts.facts("e1")
    assert "即將到來的回診" in section.title
    assert section.items == ["2026-07-12 眼科回診", "2026-07-20 心臟科回診"]


def test_none_when_no_upcoming():
    facts = _facts([("2026-07-01", "過去")])  # 早於 NOW(07-10)
    assert facts.facts("e1") is None


def test_none_when_elder_has_no_appointments():
    facts = _facts([("2026-07-20", "x")])
    assert facts.facts("e-unknown") is None
