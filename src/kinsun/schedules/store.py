"""統一排程儲存：Protocol、Postgres 實作與記憶體替身。

Store 保持 dumb：只做查詢與狀態轉移，不判斷「過期」——那需要判定窗，屬派送
邏輯（jobs 層）。這道界線正是合約測試能對兩個 adapter 用同一份斷言的前提。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.schedules.models import (
    Audience,
    CreatedBy,
    RepeatKind,
    Schedule,
    ScheduleKind,
)


class ScheduleError(Exception):
    """排程資料讀寫失敗。"""


_COLUMNS = (
    "schedule_id, group_id, elder_id, kind, title, repeat_kind, scheduled_at, "
    "repeat_time, repeat_weekday, event_at, audience, created_by, created_at, "
    "cancelled_at, settled_at, fired_at"
)

# 「目前有效」＝未取消且未結案。上限計算、清單、日後的對話注入全部共用這個定義，
# 三處各自定義是漂移的起點。
_ACTIVE = "cancelled_at IS NULL AND settled_at IS NULL"


class ScheduleStore(Protocol):
    def save(self, schedule: Schedule) -> None: ...
    def get(self, schedule_id: str) -> Schedule | None: ...
    def list_for_elder(self, elder_id: str) -> list[Schedule]: ...
    def list_for_group(self, group_id: str) -> list[Schedule]: ...
    def cancel_group(self, group_id: str, *, now: float) -> None: ...
    def list_due_once(self, *, until: float) -> list[Schedule]: ...
    def list_due_repeating(
        self, *, times: tuple[str, ...], weekday: int, not_fired_since: float
    ) -> list[Schedule]: ...
    def mark_fired(self, schedule_id: str, *, now: float) -> None: ...
    def mark_settled(self, schedule_id: str, *, now: float) -> None: ...


def _to_schedule(row: tuple) -> Schedule:
    return Schedule(
        schedule_id=row[0],
        group_id=row[1],
        elder_id=row[2],
        kind=ScheduleKind(row[3]),
        title=row[4],
        repeat_kind=RepeatKind(row[5]),
        scheduled_at=row[6],
        repeat_time=row[7],
        repeat_weekday=row[8],
        event_at=row[9],
        audience=Audience(row[10]),
        created_by=CreatedBy(row[11]),
        created_at=row[12],
        cancelled_at=row[13],
        settled_at=row[14],
        fired_at=row[15],
    )


def _is_active(schedule: Schedule) -> bool:
    return schedule.cancelled_at is None and schedule.settled_at is None


def _sort_key(schedule: Schedule) -> tuple:
    """與 Pg 的 ORDER BY scheduled_at NULLS LAST, repeat_time, title 等價。"""
    return (
        schedule.scheduled_at is None,
        schedule.scheduled_at or 0.0,
        schedule.repeat_time,
        schedule.title,
    )


class PgScheduleStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: ScheduleError(f"排程資料存取失敗：{m}"))

    def save(self, schedule: Schedule) -> None:
        self._db.execute(
            f"INSERT INTO schedules ({_COLUMNS}) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (schedule_id) DO UPDATE SET "
            "group_id = EXCLUDED.group_id, elder_id = EXCLUDED.elder_id, "
            "kind = EXCLUDED.kind, title = EXCLUDED.title, "
            "repeat_kind = EXCLUDED.repeat_kind, scheduled_at = EXCLUDED.scheduled_at, "
            "repeat_time = EXCLUDED.repeat_time, repeat_weekday = EXCLUDED.repeat_weekday, "
            "event_at = EXCLUDED.event_at, audience = EXCLUDED.audience, "
            "created_by = EXCLUDED.created_by, created_at = EXCLUDED.created_at, "
            "cancelled_at = EXCLUDED.cancelled_at, settled_at = EXCLUDED.settled_at, "
            "fired_at = EXCLUDED.fired_at",
            (
                schedule.schedule_id,
                schedule.group_id,
                schedule.elder_id,
                schedule.kind.value,
                schedule.title,
                schedule.repeat_kind.value,
                schedule.scheduled_at,
                schedule.repeat_time,
                schedule.repeat_weekday,
                schedule.event_at,
                schedule.audience.value,
                schedule.created_by.value,
                schedule.created_at,
                schedule.cancelled_at,
                schedule.settled_at,
                schedule.fired_at,
            ),
        )

    def get(self, schedule_id: str) -> Schedule | None:
        row = self._db.query_one(
            f"SELECT {_COLUMNS} FROM schedules WHERE schedule_id = %s", (schedule_id,)
        )
        return _to_schedule(row) if row else None

    def list_for_elder(self, elder_id: str) -> list[Schedule]:
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM schedules WHERE elder_id = %s AND {_ACTIVE} "
            "ORDER BY scheduled_at NULLS LAST, repeat_time, title",
            (elder_id,),
        )
        return [_to_schedule(r) for r in rows]

    def list_for_group(self, group_id: str) -> list[Schedule]:
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM schedules WHERE group_id = %s "
            "ORDER BY scheduled_at NULLS LAST, repeat_time, title",
            (group_id,),
        )
        return [_to_schedule(r) for r in rows]

    def cancel_group(self, group_id: str, *, now: float) -> None:
        # 只蓋還沒取消的列：重複取消不會改寫第一次的取消時刻——那是「他什麼時候
        # 反悔的」這個事實，健康報告與每晚反思都會回看它。
        self._db.execute(
            "UPDATE schedules SET cancelled_at = %s WHERE group_id = %s AND cancelled_at IS NULL",
            (now, group_id),
        )

    def list_due_once(self, *, until: float) -> list[Schedule]:
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM schedules "
            f"WHERE repeat_kind = %s AND {_ACTIVE} AND scheduled_at <= %s "
            "ORDER BY scheduled_at",
            (RepeatKind.ONCE.value, until),
        )
        return [_to_schedule(r) for r in rows]

    def list_due_repeating(
        self, *, times: tuple[str, ...], weekday: int, not_fired_since: float
    ) -> list[Schedule]:
        # weekly 比對星期、daily 不限；當日冪等由呼叫端傳入的 not_fired_since（今日
        # 零時）判定——store 沒有時區也不該有，時間語意一律由注入的 clock 決定。
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM schedules "
            "WHERE cancelled_at IS NULL AND repeat_time = ANY(%s) "
            "AND (repeat_kind = %s OR (repeat_kind = %s AND repeat_weekday = %s)) "
            "AND (fired_at IS NULL OR fired_at < %s) "
            "ORDER BY repeat_time, title",
            (
                list(times),
                RepeatKind.DAILY.value,
                RepeatKind.WEEKLY.value,
                weekday,
                not_fired_since,
            ),
        )
        return [_to_schedule(r) for r in rows]

    def mark_fired(self, schedule_id: str, *, now: float) -> None:
        self._db.execute(
            "UPDATE schedules SET fired_at = %s WHERE schedule_id = %s", (now, schedule_id)
        )

    def mark_settled(self, schedule_id: str, *, now: float) -> None:
        self._db.execute(
            "UPDATE schedules SET settled_at = %s WHERE schedule_id = %s", (now, schedule_id)
        )


class FakeScheduleStore:
    """ScheduleStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._rows: dict[str, Schedule] = {}

    def save(self, schedule: Schedule) -> None:
        self._rows[schedule.schedule_id] = schedule

    def get(self, schedule_id: str) -> Schedule | None:
        return self._rows.get(schedule_id)

    def list_for_elder(self, elder_id: str) -> list[Schedule]:
        rows = [s for s in self._rows.values() if s.elder_id == elder_id and _is_active(s)]
        return sorted(rows, key=_sort_key)

    def list_for_group(self, group_id: str) -> list[Schedule]:
        return sorted((s for s in self._rows.values() if s.group_id == group_id), key=_sort_key)

    def cancel_group(self, group_id: str, *, now: float) -> None:
        for schedule_id, schedule in list(self._rows.items()):
            if schedule.group_id == group_id and schedule.cancelled_at is None:
                self._rows[schedule_id] = replace(schedule, cancelled_at=now)

    def list_due_once(self, *, until: float) -> list[Schedule]:
        rows = [
            s
            for s in self._rows.values()
            if s.repeat_kind == RepeatKind.ONCE
            and _is_active(s)
            and s.scheduled_at is not None
            and s.scheduled_at <= until
        ]
        return sorted(rows, key=_sort_key)

    def list_due_repeating(
        self, *, times: tuple[str, ...], weekday: int, not_fired_since: float
    ) -> list[Schedule]:
        rows = [
            s
            for s in self._rows.values()
            if s.cancelled_at is None
            and s.repeat_time in times
            and (
                s.repeat_kind == RepeatKind.DAILY
                or (s.repeat_kind == RepeatKind.WEEKLY and s.repeat_weekday == weekday)
            )
            and (s.fired_at is None or s.fired_at < not_fired_since)
        ]
        return sorted(rows, key=_sort_key)

    def mark_fired(self, schedule_id: str, *, now: float) -> None:
        schedule = self._rows.get(schedule_id)
        if schedule is not None:
            self._rows[schedule_id] = replace(schedule, fired_at=now)

    def mark_settled(self, schedule_id: str, *, now: float) -> None:
        schedule = self._rows.get(schedule_id)
        if schedule is not None:
            self._rows[schedule_id] = replace(schedule, settled_at=now)
