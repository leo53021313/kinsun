from kinsun.accounts.models import Elder, ElderGuardian, PrincipalType, Role
from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.appointments.models import Appointment


class _FakeRouter:
    def __init__(self, deliverable=True):
        self.sent = []
        self._deliverable = deliverable

    def send_text(self, principal_type, principal_id, text):
        self.sent.append((principal_type, principal_id, text))
        return 1 if self._deliverable else 0


def _eg(guardian_id, order=1):
    return ElderGuardian("e1", guardian_id, Role.GUARDIAN, order)


def _job(appts_by_date, *, elders, guardians, hour=8, record=None, deliverable=True):
    router = _FakeRouter(deliverable=deliverable)
    job = build_appointment_reminder_job(
        appts_on=lambda d: appts_by_date.get(d, []),
        today=lambda: "2026-07-15",
        tomorrow=lambda: "2026-07-16",
        lookup_elder=lambda eid: elders.get(eid),
        guardians_of=lambda eid: [_eg(g, i + 1) for i, g in enumerate(guardians.get(eid, []))],
        router=router,
        hour=hour,
        record=record,
    )
    return job, router.sent


def test_today_and_tomorrow_to_elder_and_guardians():
    elders = {"e1": Elder("e1", "阿公")}
    appts = {
        "2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")],
        "2026-07-16": [Appointment("a2", "e1", "2026-07-16", "眼科回診")],
    }
    job, pushed = _job(appts, elders=elders, guardians={"e1": ["g-son"]})
    job.run()
    elder_msgs = [(g, t) for p, g, t in pushed if p is PrincipalType.ELDER]
    guardian_msgs = [(g, t) for p, g, t in pushed if p is PrincipalType.GUARDIAN]
    assert ("e1", "阿公，今天要回診囉：心臟科回診。記得準時，需要的話請家人陪您去。") in elder_msgs
    assert ("e1", "阿公，明天要回診囉：眼科回診。記得準時，需要的話請家人陪您去。") in elder_msgs
    assert ("g-son", "【金孫提醒】阿公 今天要回診——心臟科回診。") in guardian_msgs
    assert ("g-son", "【金孫提醒】阿公 明天要回診——眼科回診。") in guardian_msgs
    assert job.cron == "0 8 * * *"


def test_skips_unknown_elder_entirely():
    """查無此長輩（資料不一致）連家屬也不通知——訊息內容組不出來。"""
    appts = {"2026-07-15": [Appointment("a1", "e-ghost", "2026-07-15", "回診")]}
    job, pushed = _job(appts, elders={}, guardians={"e-ghost": ["g-son"]})
    job.run()
    assert pushed == []


def test_records_reminder_per_event():
    elders = {"e1": Elder("e1", "阿公")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")]}
    recorded = []
    job, _ = _job(
        appts,
        elders=elders,
        guardians={"e1": ["g-son"]},
        record=lambda e, k, c: recorded.append((e, k, c)),
    )
    job.run()
    assert recorded == [("e1", "appointment", "今天回診：心臟科回診")]


def test_no_record_when_elder_unreachable():
    """✅ 庚-14（A-34）：長輩送達 0 個通道時不記提醒紀錄——
    否則家屬健康報告會顯示長輩實際沒收到的提醒。比照用藥 job 守門。"""
    elders = {"e1": Elder("e1", "阿公")}
    appts = {"2026-07-15": [Appointment("a1", "e1", "2026-07-15", "心臟科回診")]}
    recorded = []
    job, _ = _job(
        appts,
        elders=elders,
        guardians={"e1": ["g-son"]},
        record=lambda e, k, c: recorded.append((e, k, c)),
        deliverable=False,
    )
    job.run()
    assert recorded == []


def test_elder_always_reminded_and_guardians_in_order():
    """✅ D-30（己-1）：出站不查同意——長輩一律提醒，家屬依序通知。"""
    elders = {"e1": Elder("e1", "阿公")}
    appts = {"2026-07-16": [Appointment("a1", "e1", "2026-07-16", "回診")]}
    job, pushed = _job(appts, elders=elders, guardians={"e1": ["g-son", "g-dau"]})
    job.run()
    assert pushed == [
        (PrincipalType.ELDER, "e1", "阿公，明天要回診囉：回診。記得準時，需要的話請家人陪您去。"),
        (PrincipalType.GUARDIAN, "g-son", "【金孫提醒】阿公 明天要回診——回診。"),
        (PrincipalType.GUARDIAN, "g-dau", "【金孫提醒】阿公 明天要回診——回診。"),
    ]
