import os

import pytest

from kinsun.appointments.models import Appointment
from tests.fakes import FakeAppointmentStore


def _appt(appt_id, elder_id, date, label):
    return Appointment(appt_id, elder_id, date, label)


def test_fake_store_round_trip():
    store = FakeAppointmentStore()
    store.save(_appt("a1", "e1", "2026-07-15", "心臟科回診"))
    store.save(_appt("a2", "e1", "2026-07-01", "眼科回診"))
    assert [a.date for a in store.list_for_elder("e1")] == ["2026-07-01", "2026-07-15"]
    assert [a.appt_id for a in store.list_for_date("2026-07-15")] == ["a1"]
    store.remove("a1")
    assert store.list_for_date("2026-07-15") == []


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_store_round_trip():
    from kinsun.appointments.store import PgAppointmentStore
    from kinsun.db import Database, ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    store = PgAppointmentStore(Database.open(url))
    store.save(_appt("ap", "ep", "2026-08-20", "測試回診"))
    got = store.list_for_elder("ep")[0]
    assert got.label == "測試回診"
    assert [a.appt_id for a in store.list_for_date("2026-08-20") if a.appt_id == "ap"] == ["ap"]
    store.remove("ap")
