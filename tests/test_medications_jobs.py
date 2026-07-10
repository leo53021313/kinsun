from kinsun.accounts.models import Elder, PrincipalType
from kinsun.medications.jobs import build_medication_slot_job
from kinsun.medications.models import Medication, MedicationSlot


class _FakeRouter:
    """ChannelRouter 替身：記錄 (principal_type, principal_id, text)；
    unreachable 中的本人回 0（模擬無綁定通道）。"""

    def __init__(self, unreachable=()):
        self.sent = []
        self._unreachable = set(unreachable)

    def send_text(self, principal_type, principal_id, text):
        if principal_id in self._unreachable:
            return 0
        self.sent.append((principal_type, principal_id, text))
        return 1


def _med(elder_id, name, slots):
    return Medication("x", elder_id, name, slots)


def _job(meds, *, elders, unreachable=(), hour=8, record=None):
    router = _FakeRouter(unreachable)
    job = build_medication_slot_job(
        slot=MedicationSlot.MORNING,
        meds_at_slot=lambda: meds,
        lookup_elder=lambda eid: elders.get(eid),
        router=router,
        hour=hour,
        name="medication-morning",
        record=record,
    )
    return job, router.sent


def test_merges_meds_per_elder():
    elders = {"e1": Elder("e1", "阿公")}
    meds = [
        _med("e1", "降血壓藥", (MedicationSlot.MORNING,)),
        _med("e1", "鈣片", (MedicationSlot.MORNING,)),
    ]
    job, pushed = _job(meds, elders=elders)
    job.run()
    assert pushed == [(PrincipalType.ELDER, "e1", "阿公，早上該吃藥囉：降血壓藥、鈣片")]
    assert job.cron == "0 8 * * *"


def test_skips_unknown_elder():
    """✅ D-30（己-1）：出站不查同意、照發；只有查無此長輩才略過。"""
    meds = [
        _med("e1", "藥A", (MedicationSlot.MORNING,)),
        _med("e-ghost", "藥B", (MedicationSlot.MORNING,)),
    ]
    job, pushed = _job(meds, elders={"e1": Elder("e1", "阿公")})
    job.run()
    assert [g for _, g, _ in pushed] == ["e1"]


def test_records_reminder_when_pushed():
    elders = {"e1": Elder("e1", "阿公")}
    recorded = []
    job, _ = _job(
        [_med("e1", "降血壓藥", (MedicationSlot.MORNING,))],
        elders=elders,
        record=lambda e, k, c: recorded.append((e, k, c)),
    )
    job.run()
    assert recorded == [("e1", "medication", "早上用藥：降血壓藥")]


def test_does_not_record_when_no_reachable_channel():
    # 無任何綁定通道（router 回 0）：不送也不記 reminder_log。
    elders = {"e1": Elder("e1", "阿公")}
    recorded = []
    job, pushed = _job(
        [_med("e1", "藥", (MedicationSlot.MORNING,))],
        elders=elders,
        unreachable=("e1",),
        record=lambda e, k, c: recorded.append((e, k, c)),
    )
    job.run()
    assert pushed == []
    assert recorded == []
