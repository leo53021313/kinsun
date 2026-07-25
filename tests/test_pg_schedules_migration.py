"""既有庫升級路徑：medications／appointments 遷入 schedules（連真庫，KINSUN_IT=1）。

⚠ 這條路徑**只能連真庫測**。空的測試庫測不到「舊表已經有資料」的升級情境，而那
正是遷移唯一會出錯的地方——庚-07 的遷移缺陷就是這樣溜到正式庫才爆的。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.migration import backfill_from_legacy
from kinsun.schedules.store import PgScheduleStore

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=TZ)
SLOT_HOURS = {"morning": 8, "noon": 12, "evening": 18, "bedtime": 21}


@pytest.fixture
def legacy(pg_database, ns):
    """在舊表塞資料，回傳 (db, ns)。"""
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


def _run(db) -> int:
    return backfill_from_legacy(db, slot_hours=SLOT_HOURS, appointment_hour=8, clock=lambda: NOW)


def test_medication_becomes_one_alarm_per_slot(legacy, ns):
    _run(legacy)
    rows = PgScheduleStore(legacy).list_for_group(f"{ns}m1")
    assert {r.repeat_time for r in rows} == {"08:00", "18:00"}  # morning=8、evening=18
    assert {r.repeat_kind.value for r in rows} == {"daily"}
    assert {r.title for r in rows} == {"血壓藥"}
    assert {r.kind.value for r in rows} == {"medication"}
    assert {r.created_by.value for r in rows} == {"guardian"}


def test_medication_slot_hours_come_from_settings(legacy, ns):
    backfill_from_legacy(
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


def test_rerunning_inserts_nothing_more(legacy, ns):
    first = _run(legacy)
    second = _run(legacy)
    assert first > 0
    assert second == 0  # 回傳的是真正插入的列數，重跑必須是 0
    assert len(PgScheduleStore(legacy).list_for_group(f"{ns}m1")) == 2


def test_rerunning_does_not_clobber_later_edits(legacy, ns):
    """重跑不可把家屬事後在新表上做的修改蓋回遷移當下的值。

    這正是遷移不能沿用 PgScheduleStore.save（upsert）的原因。
    """
    _run(legacy)
    store = PgScheduleStore(legacy)
    edited = store.get(f"{ns}m1-morning")
    from dataclasses import replace

    store.save(replace(edited, repeat_time="07:30"))
    _run(legacy)
    assert store.get(f"{ns}m1-morning").repeat_time == "07:30"


def test_unknown_slot_is_skipped_without_crashing(pg_database, ns):
    pg_database.execute(
        "INSERT INTO medications (medication_id, elder_id, name, slots) VALUES (%s, %s, %s, %s)",
        (f"{ns}m2", f"{ns}e1", "怪藥", "midnight"),
    )
    _run(pg_database)
    assert PgScheduleStore(pg_database).list_for_group(f"{ns}m2") == []
