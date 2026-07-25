"""ScheduleStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.schedules.models import (
    Audience,
    CreatedBy,
    RepeatKind,
    Schedule,
    ScheduleKind,
)
from kinsun.schedules.store import FakeScheduleStore, PgScheduleStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgScheduleStore(request.getfixturevalue("pg_database"))
    return FakeScheduleStore()


def _once(schedule_id: str, group_id: str, elder_id: str, at: float, **kw) -> Schedule:
    return Schedule(
        schedule_id=schedule_id,
        group_id=group_id,
        elder_id=elder_id,
        kind=kw.pop("kind", ScheduleKind.CUSTOM),
        title=kw.pop("title", "去吃飯"),
        repeat_kind=RepeatKind.ONCE,
        scheduled_at=at,
        created_at=1.0,
        **kw,
    )


def _daily(schedule_id: str, group_id: str, elder_id: str, hhmm: str, **kw) -> Schedule:
    return Schedule(
        schedule_id=schedule_id,
        group_id=group_id,
        elder_id=elder_id,
        kind=kw.pop("kind", ScheduleKind.MEDICATION),
        title=kw.pop("title", "血壓藥"),
        repeat_kind=RepeatKind.DAILY,
        repeat_time=hhmm,
        created_at=1.0,
        **kw,
    )


def test_get_returns_saved_schedule_with_all_fields(store, ns):
    saved = _once(
        f"{ns}s1",
        f"{ns}g1",
        f"{ns}e1",
        at=1000.0,
        kind=ScheduleKind.APPOINTMENT,
        title="心臟科回診",
        event_at=2000.0,
        audience=Audience.ELDER_AND_GUARDIAN,
        created_by=CreatedBy.ELDER,
    )
    store.save(saved)
    assert store.get(f"{ns}s1") == saved


def test_get_returns_none_when_absent(store, ns):
    assert store.get(f"{ns}nope") is None


def test_save_upserts_on_conflict(store, ns):
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0, title="原本"))
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=2000.0, title="改過"))
    got = store.get(f"{ns}s1")
    assert got is not None
    assert got.title == "改過"
    assert got.scheduled_at == 2000.0
    assert len(store.list_for_elder(f"{ns}e1")) == 1


def test_list_for_elder_excludes_cancelled(store, ns):
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0))
    store.save(_once(f"{ns}s2", f"{ns}g2", f"{ns}e1", at=2000.0, cancelled_at=50.0))
    assert {s.schedule_id for s in store.list_for_elder(f"{ns}e1")} == {f"{ns}s1"}


def test_list_for_elder_excludes_settled(store, ns):
    # 已結案的一次性排程不是「目前有效的事」，上限計算與清單都不該算進去。
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0))
    store.save(_once(f"{ns}s2", f"{ns}g2", f"{ns}e1", at=2000.0, settled_at=50.0))
    assert {s.schedule_id for s in store.list_for_elder(f"{ns}e1")} == {f"{ns}s1"}


def test_list_for_elder_is_scoped_to_that_elder(store, ns):
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0))
    store.save(_once(f"{ns}s2", f"{ns}g2", f"{ns}e2", at=1000.0))
    assert {s.schedule_id for s in store.list_for_elder(f"{ns}e1")} == {f"{ns}s1"}


def test_list_for_group_returns_every_alarm_of_one_thing(store, ns):
    # 同一顆藥早晚各一個鬧鐘：兩列、同 group。
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.save(_daily(f"{ns}s2", f"{ns}g1", f"{ns}e1", "21:00"))
    store.save(_daily(f"{ns}s3", f"{ns}g2", f"{ns}e1", "12:00"))
    assert {s.schedule_id for s in store.list_for_group(f"{ns}g1")} == {f"{ns}s1", f"{ns}s2"}


def test_cancel_group_cancels_every_alarm_in_it(store, ns):
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.save(_daily(f"{ns}s2", f"{ns}g1", f"{ns}e1", "21:00"))
    store.cancel_group(f"{ns}g1", now=99.0)
    assert store.list_for_elder(f"{ns}e1") == []
    assert all(s.cancelled_at == 99.0 for s in store.list_for_group(f"{ns}g1"))


def test_cancel_group_leaves_other_groups_untouched(store, ns):
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.save(_daily(f"{ns}s2", f"{ns}g2", f"{ns}e1", "21:00"))
    store.cancel_group(f"{ns}g1", now=99.0)
    assert {s.schedule_id for s in store.list_for_elder(f"{ns}e1")} == {f"{ns}s2"}


def test_cancel_group_keeps_the_first_cancellation_time(store, ns):
    # 重複取消不得改寫第一次的時刻——那是「他什麼時候反悔的」這個事實。
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.cancel_group(f"{ns}g1", now=99.0)
    store.cancel_group(f"{ns}g1", now=500.0)
    assert store.list_for_group(f"{ns}g1")[0].cancelled_at == 99.0


def test_list_due_once_returns_only_reached_alarms(store, ns):
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0))
    store.save(_once(f"{ns}s2", f"{ns}g2", f"{ns}e1", at=3000.0))
    ids = {s.schedule_id for s in store.list_due_once(until=2000.0)}
    assert f"{ns}s1" in ids
    assert f"{ns}s2" not in ids


def test_list_due_once_excludes_settled_and_cancelled(store, ns):
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0, settled_at=1500.0))
    store.save(_once(f"{ns}s2", f"{ns}g2", f"{ns}e1", at=1000.0, cancelled_at=1500.0))
    ids = {s.schedule_id for s in store.list_due_once(until=2000.0)}
    assert f"{ns}s1" not in ids
    assert f"{ns}s2" not in ids


def test_list_due_once_ignores_repeating_rows(store, ns):
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    assert f"{ns}s1" not in {s.schedule_id for s in store.list_due_once(until=9e9)}


def test_list_due_repeating_matches_any_minute_in_window(store, ns):
    # 判定窗可能橫跨兩個分鐘值（掃描抖動），故傳入的是一組 HH:MM。
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.save(_daily(f"{ns}s2", f"{ns}g2", f"{ns}e1", "08:01"))
    store.save(_daily(f"{ns}s3", f"{ns}g3", f"{ns}e1", "09:00"))
    due = store.list_due_repeating(times=("08:00", "08:01"), weekday=2, not_fired_since=0.0)
    ids = {s.schedule_id for s in due}
    assert f"{ns}s1" in ids
    assert f"{ns}s2" in ids
    assert f"{ns}s3" not in ids


def test_list_due_repeating_respects_weekday_for_weekly(store, ns):
    store.save(
        Schedule(
            schedule_id=f"{ns}s1",
            group_id=f"{ns}g1",
            elder_id=f"{ns}e1",
            kind=ScheduleKind.CUSTOM,
            title="上課",
            repeat_kind=RepeatKind.WEEKLY,
            repeat_time="15:00",
            repeat_weekday=2,
            created_at=1.0,
        )
    )
    matched = store.list_due_repeating(times=("15:00",), weekday=2, not_fired_since=0.0)
    missed = store.list_due_repeating(times=("15:00",), weekday=3, not_fired_since=0.0)
    assert f"{ns}s1" in {s.schedule_id for s in matched}
    assert f"{ns}s1" not in {s.schedule_id for s in missed}


def test_list_due_repeating_skips_already_fired_today(store, ns):
    # 當日冪等：今天送過的重複型排程不再出現在到期清單。
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00", fired_at=5000.0))
    store.save(_daily(f"{ns}s2", f"{ns}g2", f"{ns}e1", "08:00", fired_at=100.0))
    due = store.list_due_repeating(times=("08:00",), weekday=2, not_fired_since=1000.0)
    ids = {s.schedule_id for s in due}
    assert f"{ns}s1" not in ids
    assert f"{ns}s2" in ids


def test_list_due_repeating_excludes_cancelled(store, ns):
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00", cancelled_at=10.0))
    due = store.list_due_repeating(times=("08:00",), weekday=2, not_fired_since=0.0)
    assert f"{ns}s1" not in {s.schedule_id for s in due}


def test_mark_fired_records_send_time_without_settling(store, ns):
    store.save(_daily(f"{ns}s1", f"{ns}g1", f"{ns}e1", "08:00"))
    store.mark_fired(f"{ns}s1", now=777.0)
    got = store.get(f"{ns}s1")
    assert got is not None
    assert got.fired_at == 777.0
    assert got.settled_at is None  # 重複型永遠不結案


def test_mark_settled_closes_a_once_alarm_without_claiming_it_was_sent(store, ns):
    # 過期作廢的路徑：結案但沒送出，fired_at 必須維持 None，否則「最後送出時刻」說謊。
    store.save(_once(f"{ns}s1", f"{ns}g1", f"{ns}e1", at=1000.0))
    store.mark_settled(f"{ns}s1", now=888.0)
    got = store.get(f"{ns}s1")
    assert got is not None
    assert got.settled_at == 888.0
    assert got.fired_at is None
    assert f"{ns}s1" not in {s.schedule_id for s in store.list_due_once(until=9e9)}
