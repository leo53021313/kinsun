from kinsun.accounts.models import Elder
from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.appointments.models import Appointment


def _job(appts_by_date, *, elders, consented, guardians, hour=8, record=None):
    pushed = []
    job = build_appointment_reminder_job(
        appts_on=lambda d: appts_by_date.get(d, []),
        today=lambda: "2026-07-15",
        tomorrow=lambda: "2026-07-16",
        lookup_elder=lambda eid: elders.get(eid),
        is_consented_elder=lambda line: consented.get(line, False),
        guardian_line_ids=lambda eid: guardians.get(eid, []),
        push=lambda line, text: pushed.append((line, text)),
        hour=hour,
        record=record,
    )
    return job, pushed


def test_today_and_tomorrow_to_elder_and_guardians():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {
        "2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")],
        "2026-07-16": [Appointment("a2", "e1", "2026-07-16", "眼科回診")],
    }
    job, pushed = _job(
        appts, elders=elders, consented={"U-elder": True}, guardians={"e1": ["U-son"]}
    )
    job.run()
    assert ("U-elder", "阿公，今天要回診囉：心臟科回診。記得準時，需要的話請家人陪您去。") in pushed
    assert ("U-elder", "阿公，明天要回診囉：眼科回診。記得準時，需要的話請家人陪您去。") in pushed
    assert ("U-son", "【金孫提醒】阿公 今天要回診——心臟科回診。") in pushed
    assert ("U-son", "【金孫提醒】阿公 明天要回診——眼科回診。") in pushed
    assert job.cron == "0 8 * * *"


def test_elder_skipped_without_consent_but_guardians_notified():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "回診")]}
    job, pushed = _job(
        appts, elders=elders, consented={"U-elder": False}, guardians={"e1": ["U-son"]}
    )
    job.run()
    assert pushed == [("U-son", "【金孫提醒】阿公 今天要回診——回診。")]


def test_records_reminder_per_event():
    elders = {"e1": Elder("e1", "阿公", "U-elder")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")]}
    recorded = []
    job, _ = _job(
        appts,
        elders=elders,
        consented={"U-elder": True},
        guardians={"e1": ["U-son"]},
        record=lambda e, k, c: recorded.append((e, k, c)),
    )
    job.run()
    assert recorded == [("e1", "appointment", "今天回診：心臟科回診")]


def test_unbound_elder_still_notifies_guardians():
    elders = {"e1": Elder("e1", "阿公", None)}
    appts = {"2026-07-16": [Appointment("a1", "e1", "2026-07-16", "回診")]}
    job, pushed = _job(
        appts, elders=elders, consented={}, guardians={"e1": ["U-son", "U-daughter"]}
    )
    job.run()
    assert pushed == [
        ("U-son", "【金孫提醒】阿公 明天要回診——回診。"),
        ("U-daughter", "【金孫提醒】阿公 明天要回診——回診。"),
    ]
