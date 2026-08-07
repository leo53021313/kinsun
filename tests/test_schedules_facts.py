"""ScheduleFacts：把長輩的排程注入對話情境的一段。

段落標題必須與舊的 MedicationFacts／AppointmentFacts **逐字相同**——那兩段字已經
在正式 prompt 裡跑了很久，換模組不是改措辭的時機。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.schedules.facts import _TITLES, ScheduleFacts
from kinsun.schedules.models import RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import FakeScheduleStore

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 20, 0, tzinfo=TZ)


def _facts(store, kind):
    """回傳該 kind 那一段（沒有則 None），讓既有斷言維持原樣。"""
    sections = ScheduleFacts(store, clock=lambda: NOW).facts("e1")
    title = _TITLES[kind]
    return next((s for s in sections if s.title == title), None)


def _daily(schedule_id, group_id, hhmm, *, title="血壓藥", kind=ScheduleKind.MEDICATION):
    return Schedule(
        schedule_id=schedule_id,
        group_id=group_id,
        elder_id="e1",
        kind=kind,
        title=title,
        repeat_kind=RepeatKind.DAILY,
        repeat_time=hhmm,
        created_at=1.0,
    )


def _once(schedule_id, group_id, at, *, title="回診", kind=ScheduleKind.APPOINTMENT, **kw):
    return Schedule(
        schedule_id=schedule_id,
        group_id=group_id,
        elder_id="e1",
        kind=kind,
        title=title,
        repeat_kind=RepeatKind.ONCE,
        scheduled_at=at,
        created_at=1.0,
        **kw,
    )


def test_no_schedules_returns_none():
    assert _facts(FakeScheduleStore(), ScheduleKind.MEDICATION) is None


def test_medication_title_is_unchanged_from_the_old_facts():
    store = FakeScheduleStore()
    store.save(_daily("s1", "g1", "08:00"))
    section = _facts(store, ScheduleKind.MEDICATION)
    assert section.title == (
        "\n這位長者目前固定服用的藥（系統設定的提醒時段，僅供參考、非醫療指示）：\n"
    )


def test_appointment_title_is_unchanged_from_the_old_facts():
    store = FakeScheduleStore()
    event = datetime(2026, 7, 30, 10, 30, tzinfo=TZ)
    store.save(_once("s1", "g1", at=event.timestamp(), event_at=event.timestamp()))
    section = _facts(store, ScheduleKind.APPOINTMENT)
    assert section.title == "\n這位長者即將到來的回診（系統設定，僅供參考）：\n"


def test_one_medication_with_two_times_becomes_one_line():
    # 早晚各一個鬧鐘是兩列、同 group；注入時要合成一行，否則模型會以為是兩種藥。
    store = FakeScheduleStore()
    store.save(_daily("s1", "g1", "08:00"))
    store.save(_daily("s2", "g1", "21:00"))
    section = _facts(store, ScheduleKind.MEDICATION)
    assert section.items == ["血壓藥（早上、睡前）"]


def test_two_medications_become_two_lines():
    store = FakeScheduleStore()
    store.save(_daily("s1", "g1", "08:00", title="血壓藥"))
    store.save(_daily("s2", "g2", "12:00", title="胃藥"))
    section = _facts(store, ScheduleKind.MEDICATION)
    assert set(section.items) == {"血壓藥（早上）", "胃藥（中午）"}


def test_appointment_shows_its_date_and_is_not_duplicated_by_its_two_alarms():
    # 一筆回診有前一天＋當天兩個鬧鐘，注入時只該出現一行。
    store = FakeScheduleStore()
    event = datetime(2026, 7, 30, 10, 30, tzinfo=TZ)
    store.save(_once("s1", "g1", at=event.timestamp() - 86400, event_at=event.timestamp()))
    store.save(_once("s2", "g1", at=event.timestamp(), event_at=event.timestamp()))
    section = _facts(store, ScheduleKind.APPOINTMENT)
    assert section.items == ["2026-07-30 回診"]


def test_only_the_requested_kind_is_included():
    store = FakeScheduleStore()
    store.save(_daily("s1", "g1", "08:00", title="血壓藥"))
    store.save(_daily("s2", "g2", "17:00", title="散步", kind=ScheduleKind.CUSTOM))
    meds = _facts(store, ScheduleKind.MEDICATION)
    custom = _facts(store, ScheduleKind.CUSTOM)
    assert meds.items == ["血壓藥（早上）"]
    assert custom.items == ["每天 17:00 散步"]


def test_custom_weekly_says_which_weekday():
    store = FakeScheduleStore()
    store.save(
        Schedule(
            schedule_id="s1",
            group_id="g1",
            elder_id="e1",
            kind=ScheduleKind.CUSTOM,
            title="上課",
            repeat_kind=RepeatKind.WEEKLY,
            repeat_time="15:00",
            repeat_weekday=2,
            created_at=1.0,
        )
    )
    section = _facts(store, ScheduleKind.CUSTOM)
    assert section.items == ["每週三 15:00 上課"]


def test_custom_once_shows_the_event_date():
    store = FakeScheduleStore()
    at = datetime(2026, 7, 26, 20, 45, tzinfo=TZ)
    store.save(_once("s1", "g1", at=at.timestamp(), title="去吃飯", kind=ScheduleKind.CUSTOM))
    section = _facts(store, ScheduleKind.CUSTOM)
    assert section.items == ["7月26日 20:45 去吃飯"]


def test_cancelled_schedules_are_not_injected():
    store = FakeScheduleStore()
    store.save(_daily("s1", "g1", "08:00"))
    store.cancel_group("g1", now=NOW.timestamp())
    assert _facts(store, ScheduleKind.MEDICATION) is None


def test_settled_one_off_schedules_are_not_injected():
    # 已經發過的一次性提醒不是「即將到來的事」，不該還留在情境裡。
    store = FakeScheduleStore()
    past = datetime(2026, 7, 20, 9, 0, tzinfo=TZ)
    store.save(_once("s1", "g1", at=past.timestamp(), event_at=past.timestamp()))
    store.mark_settled("s1", now=past.timestamp())
    assert _facts(store, ScheduleKind.APPOINTMENT) is None


def test_three_kinds_query_the_store_only_once():
    """三段共用一次查詢——原本一個 kind 一個實例，各打一次相同的查詢。

    這是本次改動的全部理由：查詢內容一模一樣（list_for_elder(elder_id)），
    三次跨海往返只是白等。用計數替身直接釘住次數，行為測試看不出這件事。
    """
    store = FakeScheduleStore()
    store.save(_daily("m1", "g1", "0800"))
    store.save(_once("a1", "g2", int(NOW.timestamp()) + 86400))
    calls = []
    original = store.list_for_elder

    def counted(elder_id):
        calls.append(elder_id)
        return original(elder_id)

    store.list_for_elder = counted
    sections = ScheduleFacts(store, clock=lambda: NOW).facts("e1")
    assert len(calls) == 1
    assert len(sections) == 2


def test_sections_follow_medication_appointment_custom_order():
    """段落順序是 prompt 契約：用藥 → 回診 → 自訂，與註冊三個實例時的順序相同。"""
    store = FakeScheduleStore()
    store.save(_once("c1", "g3", int(NOW.timestamp()) + 3600, title="繳電費",
                     kind=ScheduleKind.CUSTOM))
    store.save(_once("a1", "g2", int(NOW.timestamp()) + 86400))
    store.save(_daily("m1", "g1", "0800"))
    sections = ScheduleFacts(store, clock=lambda: NOW).facts("e1")
    assert [s.title for s in sections] == [
        _TITLES[ScheduleKind.MEDICATION],
        _TITLES[ScheduleKind.APPOINTMENT],
        _TITLES[ScheduleKind.CUSTOM],
    ]
