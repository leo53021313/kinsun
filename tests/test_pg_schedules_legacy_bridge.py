"""過渡期對帳橋接：舊表 → schedules（連真庫，KINSUN_IT=1）。

⚠ 這條路徑**只能連真庫測**。空的測試庫測不到「舊表已經有資料」的情境，而那正是
對帳唯一會出錯的地方——庚-07 的遷移缺陷就是這樣溜到正式庫才爆的。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.legacy_bridge import reconcile_from_legacy
from kinsun.schedules.models import CreatedBy, RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import PgScheduleStore

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=TZ)
SLOT_HOURS = {"morning": 8, "noon": 12, "evening": 18, "bedtime": 21}


@pytest.fixture
def legacy(pg_database, ns):
    """在舊表塞一筆用藥與一筆回診。"""
    pg_database.execute(
        "INSERT INTO medications (medication_id, elder_id, name, slots) VALUES (%s, %s, %s, %s)",
        (f"{ns}m1", f"{ns}e1", "血壓藥", "morning,evening"),
    )
    pg_database.execute(
        "INSERT INTO appointments (appointment_id, elder_id, date, label, time) "
        "VALUES (%s, %s, %s, %s, %s)",
        (f"{ns}a1", f"{ns}e1", "2026-07-30", "心臟科回診", "10:30"),
    )
    return pg_database


def _run(db) -> tuple[int, int]:
    return reconcile_from_legacy(db, slot_hours=SLOT_HOURS, appointment_hour=8, clock=lambda: NOW)


# ── 初次遷入 ──


def test_medication_becomes_one_alarm_per_slot(legacy, ns):
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}m1")
    assert {r.repeat_time for r in rows} == {"08:00", "18:00"}  # morning=8、evening=18
    assert {r.repeat_kind.value for r in rows} == {"daily"}
    assert {r.title for r in rows} == {"血壓藥"}
    assert {r.kind.value for r in rows} == {"medication"}
    assert {r.created_by.value for r in rows} == {"guardian"}


def test_medication_slot_hours_come_from_settings(legacy, ns):
    reconcile_from_legacy(
        legacy, slot_hours={**SLOT_HOURS, "morning": 7}, appointment_hour=8, clock=lambda: NOW
    )
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}m1")
    assert "07:00" in {r.repeat_time for r in rows}


def test_appointment_becomes_two_alarms_one_day_apart(legacy, ns):
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}a1")
    assert len(rows) == 2
    moments = sorted(datetime.fromtimestamp(r.scheduled_at, TZ) for r in rows)
    assert moments[0] == datetime(2026, 7, 29, 8, 0, tzinfo=TZ)
    assert moments[1] == datetime(2026, 7, 30, 8, 0, tzinfo=TZ)


def test_appointment_keeps_its_event_time_and_notifies_the_family(legacy, ns):
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}a1")
    assert {datetime.fromtimestamp(r.event_at, TZ) for r in rows} == {
        datetime(2026, 7, 30, 10, 30, tzinfo=TZ)
    }
    assert {r.audience.value for r in rows} == {"elder_and_guardian"}


def test_appointment_without_a_time_lands_on_midnight(pg_database, ns):
    # 00:00 ＝ 未指定看診時刻（jobs._event_time 的約定），提醒因此不帶時間。
    pg_database.execute(
        "INSERT INTO appointments (appointment_id, elder_id, date, label, time) "
        "VALUES (%s, %s, %s, %s, %s)",
        (f"{ns}a2", f"{ns}e1", "2026-07-31", "牙科", ""),
    )
    _run(pg_database)
    rows = PgScheduleStore(pg_database).list_for_group(f"{ns}a2")
    assert datetime.fromtimestamp(rows[0].event_at, TZ) == datetime(2026, 7, 31, 0, 0, tzinfo=TZ)


def test_past_appointments_are_not_migrated(pg_database, ns):
    past = (NOW.date() - timedelta(days=3)).isoformat()
    pg_database.execute(
        "INSERT INTO appointments (appointment_id, elder_id, date, label, time) "
        "VALUES (%s, %s, %s, %s, %s)",
        (f"{ns}old", f"{ns}e1", past, "早就看完了", ""),
    )
    _run(pg_database)
    assert PgScheduleStore(pg_database).list_for_group(f"{ns}old") == []


def test_unknown_slot_is_skipped_without_crashing(pg_database, ns):
    pg_database.execute(
        "INSERT INTO medications (medication_id, elder_id, name, slots) VALUES (%s, %s, %s, %s)",
        (f"{ns}m2", f"{ns}e1", "怪藥", "midnight"),
    )
    _run(pg_database)
    assert PgScheduleStore(pg_database).list_for_group(f"{ns}m2") == []


def test_reconcile_writes_all_four_alarms_and_cancels_nothing(legacy, ns):
    # ⚠ 回傳的計數是**全庫**的（對帳本質就是全庫掃描），不可能 scope 到本測試的 ns，
    # 故只斷言「本測試那四列都在」與「這一輪沒有取消任何東西」。
    _, cancelled = _run(legacy)
    ids = {r.schedule_id for r in PgScheduleStore(legacy).list_for_elder(f"{ns}e1")}
    assert {f"{ns}m1-morning", f"{ns}m1-evening", f"{ns}a1-0", f"{ns}a1-1"} <= ids
    assert cancelled == 0


# ── 對帳的三條邊界（過渡期舊表是唯一真相）──


def test_rerunning_does_not_duplicate_rows(legacy, ns):
    _run(legacy)
    _run(legacy)
    assert len(PgScheduleStore(legacy).list_for_group(f"{ns}m1")) == 2


def test_a_medication_added_later_gets_picked_up(legacy, ns):
    # P2 上線後家屬用 LINE 新增的藥仍寫進舊表；沒有這條，長輩就收不到新藥的提醒。
    _run(legacy)
    legacy.execute(
        "INSERT INTO medications (medication_id, elder_id, name, slots) VALUES (%s, %s, %s, %s)",
        (f"{ns}m9", f"{ns}e1", "新藥", "noon"),
    )
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}m9")
    assert [r.repeat_time for r in rows] == ["12:00"]


def test_a_medication_deleted_later_is_cancelled(legacy, ns):
    # 沒有這條，家屬刪掉的藥會讓長輩一直收到提醒——比沒同步更糟。
    _run(legacy)
    legacy.execute("DELETE FROM medications WHERE medication_id = %s", (f"{ns}m1",))
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}m1")
    assert rows  # 列還在（軟刪）
    assert all(r.cancelled_at is not None for r in rows)


def test_an_edited_medication_is_updated_not_duplicated(legacy, ns):
    """過渡期舊表是唯一真相，故改名與改時段都要蓋過去。

    與 P1 的 store.save（upsert）不同的是：對帳只蓋內容欄，不碰 fired_at／
    settled_at——洗掉 fired_at 會讓今天已經送過的藥同一天再送一次。
    """
    _run(legacy)
    legacy.execute(
        "UPDATE medications SET name = %s, slots = %s WHERE medication_id = %s",
        ("血壓藥（新）", "morning", f"{ns}m1"),
    )
    _run(legacy)
    store = PgScheduleStore(legacy)
    active = [r for r in store.list_for_group(f"{ns}m1") if r.cancelled_at is None]
    assert [r.title for r in active] == ["血壓藥（新）"]
    assert [r.repeat_time for r in active] == ["08:00"]  # evening 那列已被取消


def test_reconcile_never_resets_a_sent_reminder(legacy, ns):
    # fired_at 被洗掉 ＝ 今天已經送過的藥同一天再送一次，正是「寧可漏不可轟炸」要防的。
    _run(legacy)
    store = PgScheduleStore(legacy)
    store.mark_fired(f"{ns}m1-morning", now=NOW.timestamp())
    _run(legacy)
    assert store.get(f"{ns}m1-morning").fired_at == NOW.timestamp()


def test_replaced_rows_keep_their_created_at(legacy, ns):
    # 對帳只蓋內容欄，created_at 不在其中——那是「這筆什麼時候進系統的」。
    _run(legacy)
    store = PgScheduleStore(legacy)
    first_created = store.get(f"{ns}m1-morning").created_at
    reconcile_from_legacy(
        legacy,
        slot_hours=SLOT_HOURS,
        appointment_hour=8,
        clock=lambda: NOW + timedelta(days=1),
    )
    assert store.get(f"{ns}m1-morning").created_at == first_created


def test_settled_rows_are_not_mistaken_for_orphans(legacy, ns):
    # 過期回診的鬧鐘早已結案，舊表查不到它是正常的，不該因此被標成取消。
    _run(legacy)
    store = PgScheduleStore(legacy)
    store.mark_settled(f"{ns}a1-1", now=NOW.timestamp())
    legacy.execute("DELETE FROM appointments WHERE appointment_id = %s", (f"{ns}a1",))
    _run(legacy)
    assert store.get(f"{ns}a1-1").cancelled_at is None
    assert store.get(f"{ns}a1-0").cancelled_at is not None  # 未結案的那列照樣取消


# ── 作用範圍：長輩自己建的排程不歸舊表管 ──


def _elder_schedule(schedule_id: str, elder_id: str, kind: ScheduleKind) -> Schedule:
    return Schedule(
        schedule_id=schedule_id,
        group_id=schedule_id,
        elder_id=elder_id,
        kind=kind,
        title="長輩自己記的事",
        repeat_kind=RepeatKind.DAILY,
        repeat_time="09:00",
        created_by=CreatedBy.ELDER,
        created_at=1.0,
    )


def test_reconcile_never_touches_what_the_elder_created(pg_database, ns):
    """少了作用範圍的限縮，P4 上線後長輩自己設的每一筆提醒都會在下次對帳被清掉。"""
    store = PgScheduleStore(pg_database)
    store.save(_elder_schedule(f"{ns}own", f"{ns}e1", ScheduleKind.CUSTOM))
    _run(pg_database)
    assert store.get(f"{ns}own").cancelled_at is None


def test_reconcile_never_touches_an_elder_created_medication(pg_database, ns):
    # 長輩用說的建的吃藥提醒 kind 也是 medication，只有 created_by 區分得出來。
    store = PgScheduleStore(pg_database)
    store.save(_elder_schedule(f"{ns}ownmed", f"{ns}e1", ScheduleKind.MEDICATION))
    _run(pg_database)
    assert store.get(f"{ns}ownmed").cancelled_at is None
