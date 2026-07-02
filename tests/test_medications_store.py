import os

import pytest

from kinsun.medications.models import Medication, MedicationSlot
from tests.fakes import FakeMedicationStore


def _med(med_id, elder_id, name, slots):
    return Medication(med_id, elder_id, name, slots)


def test_fake_store_round_trip():
    store = FakeMedicationStore()
    store.save(_med("m1", "e1", "降血壓藥", (MedicationSlot.MORNING, MedicationSlot.EVENING)))
    store.save(_med("m2", "e1", "鈣片", (MedicationSlot.BEDTIME,)))
    assert [m.name for m in store.list_for_elder("e1")] == ["鈣片", "降血壓藥"]
    assert [m.med_id for m in store.list_for_slot(MedicationSlot.MORNING)] == ["m1"]
    assert [m.med_id for m in store.list_for_slot(MedicationSlot.BEDTIME)] == ["m2"]
    store.remove("m1")
    assert [m.med_id for m in store.list_for_slot(MedicationSlot.MORNING)] == []


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_store_round_trip():
    from kinsun.db import Database, ensure_schema
    from kinsun.medications.store import PgMedicationStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    store = PgMedicationStore(Database.open(url))
    store.save(_med("mp", "ep", "測試藥", (MedicationSlot.MORNING, MedicationSlot.NOON)))
    got = store.list_for_elder("ep")[0]
    assert got.name == "測試藥"
    assert MedicationSlot.NOON in got.slots
    assert [m.med_id for m in store.list_for_slot(MedicationSlot.NOON) if m.med_id == "mp"] == [
        "mp"
    ]
    store.remove("mp")
