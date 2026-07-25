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
