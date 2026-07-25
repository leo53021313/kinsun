"""統一排程服務：把「一件事」展開成一組鬧鐘，並在寫入前擋掉壞輸入。

驗證放在 service 而非各呼叫端：建立排程有三個入口（家屬 App、LINE 選單、長輩
語音工具），規則若散在三處，最先漂移的一定是最少人看的那處——而那處正是模型
在講話。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import datetime

from kinsun.schedules.models import (
    CreatedBy,
    Occurrence,
    RepeatKind,
    Schedule,
    ScheduleGroup,
    ScheduleKind,
    audience_for,
)
from kinsun.schedules.store import ScheduleStore


class ScheduleValidationError(Exception):
    """排程輸入不合法。

    訊息一律寫成可以直接講給長輩聽的白話，工具層原樣轉述即可，不必再翻譯一次
    ——翻譯就是又一個會漂移的地方。
    """


_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleService:
    def __init__(
        self,
        store: ScheduleStore,
        *,
        clock: Callable[[], datetime],
        new_id: Callable[[], str] | None = None,
        max_active_per_elder: int = 20,
        max_days_ahead: int = 365,
    ) -> None:
        self._store = store
        self._clock = clock
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._max_active = max_active_per_elder
        self._max_days_ahead = max_days_ahead

    def create(
        self,
        *,
        elder_id: str,
        kind: ScheduleKind,
        title: str,
        created_by: CreatedBy,
        occurrences: tuple[Occurrence, ...],
        event_at: float | None = None,
    ) -> list[Schedule]:
        """把一件事展開成一組鬧鐘寫入。

        全有全無：所有 occurrence 驗證通過、且加總不超過上限，才開始寫。寫了
        一半會讓長輩拿到「半組」鬧鐘——早上會響、晚上不會，比整組沒建更難察覺。
        """
        cleaned = title.strip()
        if not cleaned:
            raise ScheduleValidationError("要提醒的事情不能是空的。")
        if not occurrences:
            raise ScheduleValidationError("至少要有一個提醒時間。")
        now = self._clock().timestamp()
        for occurrence in occurrences:
            self._validate(occurrence, now=now)
        self._check_limit(elder_id, adding=len(occurrences))

        group_id = self._new_id()
        rows = [
            Schedule(
                schedule_id=group_id if index == 0 else self._new_id(),
                group_id=group_id,
                elder_id=elder_id,
                kind=kind,
                title=cleaned,
                repeat_kind=occurrence.repeat_kind,
                scheduled_at=occurrence.scheduled_at,
                repeat_time=occurrence.repeat_time,
                repeat_weekday=occurrence.repeat_weekday,
                event_at=event_at,
                audience=audience_for(kind),
                created_by=created_by,
                created_at=now,
            )
            for index, occurrence in enumerate(occurrences)
        ]
        for row in rows:
            self._store.save(row)
        return rows

    def list_for_elder(self, elder_id: str) -> list[Schedule]:
        return self._store.list_for_elder(elder_id)

    def groups_for_elder(
        self, elder_id: str, *, kind: ScheduleKind | None = None
    ) -> list[ScheduleGroup]:
        """把鬧鐘收斂成「一件事」。家屬與長輩看到的一律是這個單位。"""
        grouped: dict[str, list[Schedule]] = {}
        for row in self._store.list_for_elder(elder_id):
            if kind is not None and row.kind != kind:
                continue
            grouped.setdefault(row.group_id, []).append(row)
        return [
            ScheduleGroup(
                group_id=group_id,
                elder_id=rows[0].elder_id,
                kind=rows[0].kind,
                title=rows[0].title,
                created_by=rows[0].created_by,
                schedules=tuple(rows),
            )
            for group_id, rows in grouped.items()
        ]

    def replace_group(
        self,
        group_id: str,
        *,
        title: str,
        occurrences: tuple[Occurrence, ...],
        event_at: float | None = None,
    ) -> list[Schedule]:
        """換掉一件事的內容與全部鬧鐘，group_id 不變。

        kind／elder_id／created_by 一律沿用原本那組——改內容不該讓一筆家屬設的藥
        變成長輩設的，也不該讓用藥變成回診。

        先驗證再動手：驗證失敗時原本那組必須原封不動，半套的修改（新時刻建好了、
        舊時刻還在響）比不修改更難察覺。
        """
        cleaned = title.strip()
        if not cleaned:
            raise ScheduleValidationError("要提醒的事情不能是空的。")
        if not occurrences:
            raise ScheduleValidationError("至少要有一個提醒時間。")
        existing = self._store.list_for_group(group_id)
        active = [s for s in existing if s.cancelled_at is None]
        if not active:
            raise ScheduleValidationError("找不到這筆提醒。")
        now = self._clock().timestamp()
        for occurrence in occurrences:
            self._validate(occurrence, now=now)

        template = active[0]
        self._store.cancel_group(group_id, now=now)
        rows = [
            Schedule(
                schedule_id=self._new_id(),
                group_id=group_id,
                elder_id=template.elder_id,
                kind=template.kind,
                title=cleaned,
                repeat_kind=occurrence.repeat_kind,
                scheduled_at=occurrence.scheduled_at,
                repeat_time=occurrence.repeat_time,
                repeat_weekday=occurrence.repeat_weekday,
                event_at=event_at,
                audience=audience_for(template.kind),
                created_by=template.created_by,
                created_at=now,
            )
            for occurrence in occurrences
        ]
        for row in rows:
            self._store.save(row)
        return rows

    def cancel_group(self, group_id: str, *, requested_by: CreatedBy) -> None:
        """取消一件事的全部鬧鐘。

        長輩不能取消家屬設的排程：吃藥與回診是家人替他把關的事，一句「不要再
        提醒我吃藥了」就刪掉，等於讓系統幫忙他停藥。反向（家屬取消長輩設的）
        則放行。

        查無此組則靜默——重複取消不該炸，呼叫端也不必先查一次。
        """
        rows = self._store.list_for_group(group_id)
        if not rows:
            return
        if requested_by == CreatedBy.ELDER and rows[0].created_by == CreatedBy.GUARDIAN:
            raise ScheduleValidationError("這是家人幫您設定的，要取消的話我跟他們說一聲好嗎？")
        self._store.cancel_group(group_id, now=self._clock().timestamp())

    def _validate(self, occurrence: Occurrence, *, now: float) -> None:
        if occurrence.repeat_kind == RepeatKind.ONCE:
            at = occurrence.scheduled_at
            if at is None:
                raise ScheduleValidationError("一次性的提醒要有確切時間。")
            if at <= now:
                raise ScheduleValidationError("那個時間已經過去了。")
            if at > now + self._max_days_ahead * 86400:
                raise ScheduleValidationError("那個時間太遠了。")
            return
        if not _HHMM.match(occurrence.repeat_time):
            raise ScheduleValidationError("重複提醒要有正確的時刻。")
        if occurrence.repeat_kind == RepeatKind.WEEKLY and occurrence.repeat_weekday is None:
            raise ScheduleValidationError("每週提醒要說是星期幾。")

    def _check_limit(self, elder_id: str, *, adding: int) -> None:
        active = len(self._store.list_for_elder(elder_id))
        if active + adding > self._max_active:
            raise ScheduleValidationError("您記的事情有點太多了，要不要先取消幾件？")
