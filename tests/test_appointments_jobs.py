from kinsun.accounts.models import Elder, ElderGuardian, PrincipalType, Role
from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.appointments.models import Appointment


class _FakeRouter:
    def __init__(self):
        self.sent = []

    def send_text(self, principal_type, principal_id, text):
        self.sent.append((principal_type, principal_id, text))
        return 1


def _eg(guardian_id, order=1):
    return ElderGuardian("e1", guardian_id, Role.GUARDIAN, order, False)


def _job(appts_by_date, *, elders, consented, guardians, hour=8, record=None):
    router = _FakeRouter()
    job = build_appointment_reminder_job(
        appts_on=lambda d: appts_by_date.get(d, []),
        today=lambda: "2026-07-15",
        tomorrow=lambda: "2026-07-16",
        lookup_elder=lambda eid: elders.get(eid),
        has_valid_consent=lambda elder_id: consented.get(elder_id, False),
        guardians_of=lambda eid: [_eg(g, i + 1) for i, g in enumerate(guardians.get(eid, []))],
        router=router,
        hour=hour,
        record=record,
    )
    return job, router.sent


def test_today_and_tomorrow_to_elder_and_guardians():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {
        "2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")],
        "2026-07-16": [Appointment("a2", "e1", "2026-07-16", "眼科回診")],
    }
    job, pushed = _job(appts, elders=elders, consented={"e1": True}, guardians={"e1": ["g-son"]})
    job.run()
    elder_msgs = [(g, t) for p, g, t in pushed if p is PrincipalType.ELDER]
    guardian_msgs = [(g, t) for p, g, t in pushed if p is PrincipalType.GUARDIAN]
    assert ("e1", "阿公，今天要回診囉：心臟科回診。記得準時，需要的話請家人陪您去。") in elder_msgs
    assert ("e1", "阿公，明天要回診囉：眼科回診。記得準時，需要的話請家人陪您去。") in elder_msgs
    assert ("g-son", "【金孫提醒】阿公 今天要回診——心臟科回診。") in guardian_msgs
    assert ("g-son", "【金孫提醒】阿公 明天要回診——眼科回診。") in guardian_msgs
    assert job.cron == "0 8 * * *"


def test_elder_skipped_without_consent_but_guardians_notified():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "回診")]}
    job, pushed = _job(appts, elders=elders, consented={"e1": False}, guardians={"e1": ["g-son"]})
    job.run()
    assert pushed == [(PrincipalType.GUARDIAN, "g-son", "【金孫提醒】阿公 今天要回診——回診。")]


def test_records_reminder_per_event():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")]}
    recorded = []
    job, _ = _job(
        appts,
        elders=elders,
        consented={"e1": True},
        guardians={"e1": ["g-son"]},
        record=lambda e, k, c: recorded.append((e, k, c)),
    )
    job.run()
    assert recorded == [("e1", "appointment", "今天回診：心臟科回診")]


def test_unconsented_elder_still_notifies_guardians_in_order():
    elders = {"e1": Elder("e1", "阿公", None)}
    appts = {"2026-07-16": [Appointment("a1", "e1", "2026-07-16", "回診")]}
    job, pushed = _job(appts, elders=elders, consented={}, guardians={"e1": ["g-son", "g-dau"]})
    job.run()
    assert pushed == [
        (PrincipalType.GUARDIAN, "g-son", "【金孫提醒】阿公 明天要回診——回診。"),
        (PrincipalType.GUARDIAN, "g-dau", "【金孫提醒】阿公 明天要回診——回診。"),
    ]
