"""schedule-dispatch job：到期送出、過期作廢、當日冪等、聚合與家屬同送。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.accounts.models import PrincipalType
from kinsun.notifications.models import NotificationSeverity
from kinsun.schedules.jobs import build_schedule_dispatch_job
from kinsun.schedules.models import (
    Audience,
    RepeatKind,
    Schedule,
    ScheduleKind,
)
from kinsun.schedules.store import FakeScheduleStore

TZ = ZoneInfo("Asia/Taipei")


class _Elder:
    def __init__(self, name: str) -> None:
        self.name = name


class _Guardian:
    def __init__(self, guardian_id: str) -> None:
        self.guardian_id = guardian_id


class _Router:
    """記錄送出的（principal_type, principal_id, text）；送達數可控。"""

    def __init__(self, *, sent: int = 1) -> None:
        self.messages: list[tuple] = []
        # 每次送出的呈現分級（2026-08-01）：messages 維持三元組不動，既有斷言不受影響。
        self.severities: list = []
        self._sent = sent

    def send_text(
        self, principal_type, principal_id, text, *, severity=NotificationSeverity.NOTICE
    ) -> int:
        self.messages.append((principal_type, principal_id, text))
        self.severities.append(severity)
        return self._sent


def _job(
    store,
    router,
    *,
    now: datetime,
    record=None,
    window_seconds: int = 90,
    guardians=(),
    elder_name: str = "阿嬤",
    known_elders: tuple[str, ...] = ("e1",),
):
    return build_schedule_dispatch_job(
        store=store,
        lookup_elder=lambda eid: _Elder(elder_name) if eid in known_elders else None,
        guardians_of=lambda _: list(guardians),
        router=router,
        clock=lambda: now,
        window_seconds=window_seconds,
        record=record,
    )


def _daily(schedule_id, elder_id, hhmm, *, title="血壓藥", kind=ScheduleKind.MEDICATION):
    return Schedule(
        schedule_id=schedule_id,
        group_id=schedule_id,
        elder_id=elder_id,
        kind=kind,
        title=title,
        repeat_kind=RepeatKind.DAILY,
        repeat_time=hhmm,
        created_at=1.0,
    )


def _once(schedule_id, elder_id, at, *, title="去吃飯", kind=ScheduleKind.CUSTOM, **kw):
    return Schedule(
        schedule_id=schedule_id,
        group_id=schedule_id,
        elder_id=elder_id,
        kind=kind,
        title=title,
        repeat_kind=RepeatKind.ONCE,
        scheduled_at=at,
        created_at=1.0,
        **kw,
    )


def test_job_runs_every_minute():
    job = _job(FakeScheduleStore(), _Router(), now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ))
    assert job.cron == "* * * * *"


def test_daily_medication_fires_at_its_minute():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00"))
    _job(store, router, now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ)).run()
    assert router.messages == [(PrincipalType.ELDER, "e1", "阿嬤，早上該吃藥囉：血壓藥")]


def test_daily_medication_does_not_fire_at_another_minute():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00"))
    _job(store, router, now=datetime(2026, 7, 25, 9, 0, tzinfo=TZ)).run()
    assert router.messages == []


def test_multiple_medications_at_the_same_time_become_one_message():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00", title="血壓藥"))
    store.save(_daily("s2", "e1", "08:00", title="胃藥"))
    _job(store, router, now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ)).run()
    assert len(router.messages) == 1
    assert "血壓藥" in router.messages[0][2]
    assert "胃藥" in router.messages[0][2]


def test_medications_in_the_same_hour_merge_even_across_window_minutes():
    # 判定窗涵蓋 08:00 與 08:01 兩分鐘，聚合鍵是「長輩＋時段小時」，故仍為一則。
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00", title="血壓藥"))
    store.save(_daily("s2", "e1", "08:01", title="胃藥"))
    _job(store, router, now=datetime(2026, 7, 25, 8, 1, tzinfo=TZ), window_seconds=90).run()
    assert len(router.messages) == 1


def test_medications_of_different_elders_never_merge():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00", title="血壓藥"))
    store.save(_daily("s2", "e2", "08:00", title="胃藥"))
    _job(
        store,
        router,
        now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ),
        known_elders=("e1", "e2"),
    ).run()
    assert {m[1] for m in router.messages} == {"e1", "e2"}


def test_repeating_schedule_is_not_sent_twice_in_one_day():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00"))
    now = datetime(2026, 7, 25, 8, 0, tzinfo=TZ)
    _job(store, router, now=now).run()
    _job(store, router, now=now).run()
    assert len(router.messages) == 1


def test_repeating_schedule_fires_again_the_next_day():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "e1", "08:00"))
    _job(store, router, now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ)).run()
    _job(store, router, now=datetime(2026, 7, 26, 8, 0, tzinfo=TZ)).run()
    assert len(router.messages) == 2


def test_weekly_schedule_only_fires_on_its_weekday():
    store, router = FakeScheduleStore(), _Router()
    store.save(
        Schedule(
            schedule_id="s1",
            group_id="s1",
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="上課",
            repeat_kind=RepeatKind.WEEKLY,
            repeat_time="15:00",
            repeat_weekday=2,  # 週三
            created_at=1.0,
        )
    )
    _job(store, router, now=datetime(2026, 7, 28, 15, 0, tzinfo=TZ)).run()  # 週二
    assert router.messages == []
    _job(store, router, now=datetime(2026, 7, 29, 15, 0, tzinfo=TZ)).run()  # 週三
    assert len(router.messages) == 1


def test_once_schedule_within_the_window_is_sent_and_settled():
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 25, 20, 45, tzinfo=TZ)
    store.save(_once("s1", "e1", at=now.timestamp()))
    _job(store, router, now=now).run()
    assert router.messages == [(PrincipalType.ELDER, "e1", "阿嬤，提醒您：去吃飯。")]
    got = store.get("s1")
    assert got.settled_at is not None
    assert got.fired_at is not None


def test_once_schedule_older_than_the_window_is_settled_without_sending():
    # 過期就不發：只結案、不送，否則長輩吃完飯之後才被叫去吃飯。
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 25, 21, 0, tzinfo=TZ)
    store.save(_once("s1", "e1", at=now.timestamp() - 600))
    _job(store, router, now=now, window_seconds=90).run()
    assert router.messages == []
    got = store.get("s1")
    assert got.settled_at is not None
    assert got.fired_at is None  # 沒送出就不可謊稱送過


def test_once_schedule_in_the_future_is_left_alone():
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 25, 20, 0, tzinfo=TZ)
    store.save(_once("s1", "e1", at=now.timestamp() + 3600))
    _job(store, router, now=now).run()
    assert router.messages == []
    assert store.get("s1").settled_at is None


def test_custom_with_lead_time_says_how_long_until_the_event():
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 25, 20, 45, tzinfo=TZ)
    event = datetime(2026, 7, 25, 21, 0, tzinfo=TZ)
    store.save(_once("s1", "e1", at=now.timestamp(), title="出門", event_at=event.timestamp()))
    _job(store, router, now=now).run()
    assert router.messages[0][2] == "阿嬤，再過 15 分鐘要出門囉。"


def test_appointment_notifies_the_elder_and_the_family():
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 29, 9, 0, tzinfo=TZ)
    event = datetime(2026, 7, 30, 10, 30, tzinfo=TZ)
    store.save(
        _once(
            "s1",
            "e1",
            at=now.timestamp(),
            title="心臟科回診",
            kind=ScheduleKind.APPOINTMENT,
            event_at=event.timestamp(),
            audience=Audience.ELDER_AND_GUARDIAN,
        )
    )
    _job(store, router, now=now, guardians=(_Guardian("g1"),), elder_name="阿公").run()
    elder_msg = next(m[2] for m in router.messages if m[0] == PrincipalType.ELDER)
    guardian_msg = next(m[2] for m in router.messages if m[0] == PrincipalType.GUARDIAN)
    assert elder_msg == ("阿公，明天 10:30 要回診囉：心臟科回診。記得準時，需要的話請家人陪您去。")
    assert guardian_msg == "【金孫提醒】阿公 明天 10:30 要回診——心臟科回診。"


def test_appointment_without_a_known_time_omits_it():
    # event_at 落在當日 00:00 ＝ 未指定看診時刻（庚-15 的舊語意）。
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 30, 9, 0, tzinfo=TZ)
    event = datetime(2026, 7, 30, 0, 0, tzinfo=TZ)
    store.save(
        _once(
            "s1",
            "e1",
            at=now.timestamp(),
            title="牙科",
            kind=ScheduleKind.APPOINTMENT,
            event_at=event.timestamp(),
            audience=Audience.ELDER_AND_GUARDIAN,
        )
    )
    _job(store, router, now=now, guardians=(_Guardian("g1"),), elder_name="阿公").run()
    elder_msg = next(m[2] for m in router.messages if m[0] == PrincipalType.ELDER)
    assert elder_msg == "阿公，今天要回診囉：牙科。記得準時，需要的話請家人陪您去。"


def test_family_is_notified_even_when_the_elder_is_unreachable():
    # 家屬通知不受長輩可達性影響——收到可口頭轉告（appointments/jobs.py 舊行為）。
    store, router = FakeScheduleStore(), _Router(sent=0)
    now = datetime(2026, 7, 30, 9, 0, tzinfo=TZ)
    store.save(
        _once(
            "s1",
            "e1",
            at=now.timestamp(),
            title="牙科",
            kind=ScheduleKind.APPOINTMENT,
            event_at=datetime(2026, 7, 30, 0, 0, tzinfo=TZ).timestamp(),
            audience=Audience.ELDER_AND_GUARDIAN,
        )
    )
    _job(store, router, now=now, guardians=(_Guardian("g1"),), elder_name="阿公").run()
    assert any(m[0] == PrincipalType.GUARDIAN for m in router.messages)


def test_cancelled_schedule_is_never_sent():
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 25, 8, 0, tzinfo=TZ)
    store.save(_daily("s1", "e1", "08:00"))
    store.cancel_group("s1", now=now.timestamp() - 100)
    _job(store, router, now=now).run()
    assert router.messages == []


def test_unknown_elder_is_skipped():
    store, router = FakeScheduleStore(), _Router()
    store.save(_daily("s1", "ghost", "08:00"))
    _job(store, router, now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ)).run()
    assert router.messages == []


def test_nothing_is_logged_when_no_channel_delivered():
    # 庚-14：沒送到的提醒不該出現在家屬的健康報告裡。
    store, router = FakeScheduleStore(), _Router(sent=0)
    recorded = []
    store.save(_daily("s1", "e1", "08:00"))
    _job(
        store,
        router,
        now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ),
        record=lambda *a: recorded.append(a),
    ).run()
    assert recorded == []


def test_a_delivered_reminder_is_logged_with_its_kind():
    store, router = FakeScheduleStore(), _Router()
    recorded = []
    store.save(_daily("s1", "e1", "08:00"))
    _job(
        store,
        router,
        now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ),
        record=lambda *a: recorded.append(a),
    ).run()
    assert len(recorded) == 1
    assert recorded[0][0] == "e1"
    assert recorded[0][1] == "medication"


def test_one_failing_item_does_not_stop_the_others():
    # 逐筆隔離（fanout 既有語意）：兩位長輩同時到期，其中一位送出時炸掉，
    # 另一位仍須收到。用不同長輩而非不同時刻，兩筆才會真的同輪到期。
    class _FlakyRouter(_Router):
        def send_text(self, principal_type, principal_id, text):
            if principal_id == "boom":
                raise RuntimeError("送不出去")
            return super().send_text(principal_type, principal_id, text)

    store, router = FakeScheduleStore(), _FlakyRouter()
    store.save(_daily("s1", "boom", "08:00", title="壞掉藥"))
    store.save(_daily("s2", "e1", "08:00", title="好藥"))
    _job(
        store,
        router,
        now=datetime(2026, 7, 25, 8, 0, tzinfo=TZ),
        known_elders=("e1", "boom"),
    ).run()
    assert [m[1] for m in router.messages] == ["e1"]


def test_reminders_go_out_as_notice_never_alert():
    """用藥／回診提醒一律是一般通知，不可染成紅色危急警報（2026-08-01）。

    ⚠️ 這條守的是「警報的稀有性」：全庫只有 `safety/notifier.py` 送得出 `alert`。
    提醒若也變成警報，家屬每天會看到好幾則紅色橫幅，真正的危急警報就被淹掉——
    2026-07-26 全流程實測報告記下的「狼來了」效應，正是這個機制的失效方式。
    長輩端與家屬端兩則都要驗：只驗其中一則的話，另一條路徑改壞了不會被發現。
    """
    store, router = FakeScheduleStore(), _Router()
    now = datetime(2026, 7, 29, 9, 0, tzinfo=TZ)
    event = datetime(2026, 7, 30, 10, 30, tzinfo=TZ)
    # 回診＋ELDER_AND_GUARDIAN：一次同時走到長輩端與家屬端兩條出站路徑。
    store.save(
        _once(
            "s1",
            "e1",
            at=now.timestamp(),
            title="心臟科回診",
            kind=ScheduleKind.APPOINTMENT,
            event_at=event.timestamp(),
            audience=Audience.ELDER_AND_GUARDIAN,
        )
    )
    _job(store, router, now=now, guardians=(_Guardian("g1"),), elder_name="阿公").run()

    # 兩條路徑都真的送出了（否則下面的 set 斷言會在空集合上空轉通過）。
    assert {m[0] for m in router.messages} == {PrincipalType.ELDER, PrincipalType.GUARDIAN}
    assert set(router.severities) == {NotificationSeverity.NOTICE}
