from itertools import count

from kinsun.medications.models import MedicationSlot
from kinsun.medications.service import MedicationService
from tests.fakes import FakeMedicationStore


def _service(store):
    ids = (f"m{i}" for i in count(1))
    return MedicationService(store, new_id=lambda: next(ids))


def test_add_and_list_and_remove():
    store = FakeMedicationStore()
    svc = _service(store)
    med = svc.add("e1", "降血壓藥", (MedicationSlot.MORNING, MedicationSlot.EVENING))
    assert med.med_id == "m1"
    assert med.name == "降血壓藥"
    assert svc.list_for_elder("e1")[0].slots == (MedicationSlot.MORNING, MedicationSlot.EVENING)
    svc.remove("m1")
    assert svc.list_for_elder("e1") == []


def test_update_replaces_name_and_slots():
    store = FakeMedicationStore()
    svc = _service(store)
    med = svc.add("e1", "舊", (MedicationSlot.MORNING,))
    svc.update(med.med_id, "e1", "新", (MedicationSlot.EVENING,))
    rows = svc.list_for_elder("e1")
    assert len(rows) == 1
    assert rows[0].name == "新"
    assert rows[0].slots == (MedicationSlot.EVENING,)
