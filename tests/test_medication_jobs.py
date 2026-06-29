from kinsun.accounts.models import Elder
from kinsun.medication.jobs import build_medication_slot_job
from kinsun.medication.models import Medication, MedicationSlot


def _med(elder_id, name, slots):
    return Medication("x", elder_id, name, slots)


def _job(meds, *, elders, consented, hour=8):
    pushed = []
    job = build_medication_slot_job(
        slot=MedicationSlot.MORNING,
        meds_at_slot=lambda: meds,
        lookup_elder=lambda eid: elders.get(eid),
        is_consented=lambda line: consented.get(line, False),
        push=lambda line, text: pushed.append((line, text)),
        hour=hour,
        name="medication-morning",
    )
    return job, pushed


def test_merges_meds_per_elder():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    consented = {"U-elder": True}
    meds = [
        _med("e1", "降血壓藥", (MedicationSlot.MORNING,)),
        _med("e1", "鈣片", (MedicationSlot.MORNING,)),
    ]
    job, pushed = _job(meds, elders=elders, consented=consented)
    job.run()
    assert pushed == [("U-elder", "阿公，早上該吃藥囉：降血壓藥、鈣片")]
    assert job.cron == "0 8 * * *"


def test_skips_unconsented_and_unbound():
    elders = {"e1": Elder("e1", "阿公", "U-elder"), "e2": Elder("e2", "阿嬤", None)}
    consented = {"U-elder": False}
    meds = [
        _med("e1", "藥A", (MedicationSlot.MORNING,)),
        _med("e2", "藥B", (MedicationSlot.MORNING,)),
    ]
    job, pushed = _job(meds, elders=elders, consented=consented)
    job.run()
    assert pushed == []


def test_single_elder_failure_isolated():
    elders = {"e1": Elder("e1", "阿公", "U-1"), "e2": Elder("e2", "阿嬤", "U-2")}
    pushed = []

    def push(line, text):
        if line == "U-1":
            raise RuntimeError("boom")
        pushed.append((line, text))

    job = build_medication_slot_job(
        slot=MedicationSlot.MORNING,
        meds_at_slot=lambda: [
            _med("e1", "藥A", (MedicationSlot.MORNING,)),
            _med("e2", "藥B", (MedicationSlot.MORNING,)),
        ],
        lookup_elder=lambda eid: elders.get(eid),
        is_consented=lambda line: True,
        push=push,
        hour=8,
        name="medication-morning",
    )
    job.run()
    assert pushed == [("U-2", "阿嬤，早上該吃藥囉：藥B")]
