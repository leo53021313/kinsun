from itertools import count

from kinsun.appointments.service import AppointmentService
from tests.fakes import FakeAppointmentStore


def _svc():
    ids = (f"a{i}" for i in count(1))
    return AppointmentService(FakeAppointmentStore(), new_id=lambda: next(ids))


def test_add_assigns_id_and_persists():
    svc = _svc()
    appt = svc.add("e1", "2026-07-15", "心臟科回診")
    assert appt.appt_id == "a1"
    assert [a.label for a in svc.list_for_elder("e1")] == ["心臟科回診"]


def test_upcoming_filters_past_keeps_today():
    svc = _svc()
    svc.add("e1", "2026-07-01", "過去")
    svc.add("e1", "2026-07-10", "今天")
    svc.add("e1", "2026-07-20", "未來")
    assert [a.label for a in svc.upcoming("e1", "2026-07-10")] == ["今天", "未來"]


def test_remove():
    svc = _svc()
    appt = svc.add("e1", "2026-07-15", "x")
    svc.remove(appt.appt_id)
    assert svc.list_for_elder("e1") == []


def test_update_replaces_date_and_label():
    svc = _svc()
    appt = svc.add("e1", "2026-07-15", "舊")
    svc.update(appt.appt_id, "e1", "2026-08-01", "新")
    rows = svc.list_for_elder("e1")
    assert len(rows) == 1
    assert rows[0].date == "2026-08-01"
    assert rows[0].label == "新"
