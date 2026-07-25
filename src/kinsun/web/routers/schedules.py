"""排程資源：CRUD（家屬替長輩設定用藥、回診與其他提醒）。

取代 medications／appointments 兩支 router。操作單位一律是 **group（一件事）**
而非單一鬧鐘：家屬按下刪除時想刪的是「這個藥」，不是「這個藥的早上那次」。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun.schedules.models import CreatedBy, Occurrence, ScheduleGroup, ScheduleKind
from kinsun.schedules.service import ScheduleService, ScheduleValidationError
from kinsun.schedules.timeparse import TimeParseError, build_occurrence, parse_epoch
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class OccurrenceIn(BaseModel):
    repeat: str  # once | daily | weekly
    time: str = ""  # 'HH:MM'
    date: str = ""  # 'YYYY-MM-DD'，once 用
    weekday: int | None = None  # 0–6，weekly 用（0 是星期一）


class ScheduleIn(BaseModel):
    kind: str  # medication | appointment | custom
    title: str
    occurrences: list[OccurrenceIn]
    event_date: str = ""  # 選填：事件本身的日期（回診看診日）
    event_time: str = ""  # 選填：事件本身的時刻


def _occurrence_json(schedule) -> dict:
    return {
        "schedule_id": schedule.schedule_id,
        "repeat": schedule.repeat_kind.value,
        "time": schedule.repeat_time,
        "weekday": schedule.repeat_weekday,
        "scheduled_at": schedule.scheduled_at,
    }


def _group_json(group: ScheduleGroup) -> dict:
    return {
        "group_id": group.group_id,
        "kind": group.kind.value,
        "title": group.title,
        "created_by": group.created_by.value,
        "event_at": group.event_at,
        "occurrences": [_occurrence_json(s) for s in group.schedules],
    }


def create_schedules_router(
    *,
    schedules: ScheduleService,
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(tags=["schedules"])

    def parse_kind(raw: str) -> ScheduleKind:
        try:
            return ScheduleKind(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_KIND) from exc

    def parse_occurrences(raw: list[OccurrenceIn]) -> tuple[Occurrence, ...]:
        if not raw:
            raise HTTPException(status_code=400, detail=ErrorCode.OCCURRENCES_REQUIRED)
        now = clock()
        try:
            return tuple(
                build_occurrence(
                    repeat=item.repeat,
                    time_text=item.time,
                    date_text=item.date,
                    weekday=item.weekday,
                    now=now,
                )
                for item in raw
            )
        except TimeParseError as exc:
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_TIME) from exc

    def parse_event_at(body: ScheduleIn) -> float | None:
        if not body.event_date:
            return None
        try:
            return parse_epoch(body.event_date, body.event_time, now=clock())
        except TimeParseError as exc:
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_DATE) from exc

    def find_group(elder_id: str, group_id: str) -> ScheduleGroup:
        for group in schedules.groups_for_elder(elder_id):
            if group.group_id == group_id:
                return group
        raise HTTPException(status_code=404, detail=ErrorCode.SCHEDULE_NOT_FOUND)

    @router.get("/elders/{elder_id}/schedules")
    def list_schedules(
        elder_id: str, kind: str = "", auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        chosen = parse_kind(kind) if kind else None
        return ok([_group_json(g) for g in schedules.groups_for_elder(elder_id, kind=chosen)])

    @router.post("/elders/{elder_id}/schedules", status_code=201)
    def create_schedule(
        elder_id: str, body: ScheduleIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        kind = parse_kind(body.kind)
        occurrences = parse_occurrences(body.occurrences)
        try:
            rows = schedules.create(
                elder_id=elder_id,
                kind=kind,
                title=body.title,
                # 走這支 API 的一律是家屬——長輩沒有 App 帳號可以打這裡。
                created_by=CreatedBy.GUARDIAN,
                occurrences=occurrences,
                event_at=parse_event_at(body),
            )
        except ScheduleValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ok(_group_json(find_group(elder_id, rows[0].group_id)))

    @router.put("/elders/{elder_id}/schedules/{group_id}")
    def update_schedule(
        elder_id: str,
        group_id: str,
        body: ScheduleIn,
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        find_group(elder_id, group_id)  # 不屬於這位長輩就 404，不洩漏他人資料
        occurrences = parse_occurrences(body.occurrences)
        try:
            schedules.replace_group(
                group_id,
                title=body.title,
                occurrences=occurrences,
                event_at=parse_event_at(body),
            )
        except ScheduleValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ok(_group_json(find_group(elder_id, group_id)))

    @router.delete("/elders/{elder_id}/schedules/{group_id}", status_code=204)
    def delete_schedule(
        elder_id: str, group_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> None:
        scope.assert_manages(auth, elder_id)
        find_group(elder_id, group_id)
        # 家屬可以取消長輩自己設的（反向才禁止），故 requested_by 固定為 GUARDIAN。
        schedules.cancel_group(group_id, requested_by=CreatedBy.GUARDIAN)

    return router
