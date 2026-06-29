from kinsun.medication.models import MedicationSlot, slots_label


def test_slot_values():
    assert MedicationSlot.MORNING.value == "morning"
    assert MedicationSlot.BEDTIME.value == "bedtime"


def test_slots_label_ordered():
    assert slots_label((MedicationSlot.EVENING, MedicationSlot.MORNING)) == "早上、晚上"
    assert slots_label(()) == ""
