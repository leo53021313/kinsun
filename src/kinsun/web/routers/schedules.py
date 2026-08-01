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
from kinsun.schedules.timeparse import (
    TimeParseError,
    build_appointment_reminders,
    build_occurrence,
    parse_epoch,
)
from kinsun.schedules.wording import appointment_day_before_skipped_text
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


def _meta(warnings: list[str]) -> dict | None:
    """有話要對家屬說才給 meta，沒有就維持 `null`（其餘端點的常態）。

    形狀比照 `GET /admin/jobs` 的 `meta.warnings`：一串可直接顯示的繁中人話。
    這裡永遠只有一則（回診前一天那顆過期沒建），用陣列是因為呼叫端的規則因此不必
    隨新增第二種提示而改寫——「有就逐條顯示」對一則與對三則是同一段程式碼。
    """
    return {"warnings": warnings} if warnings else None


def create_schedules_router(
    *,
    schedules: ScheduleService,
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
    clock: Callable[[], datetime],
    appointment_hour: int,
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

    def plan(
        body: ScheduleIn, kind: ScheduleKind
    ) -> tuple[tuple[Occurrence, ...], float | None, list[str]]:
        """回傳（鬧鐘, 事件時刻, 要告訴家屬的話）。

        **回診（帶 `event_date`）的鬧鐘由後端自己算，client 送的 `occurrences` 一律忽略**
        （12 §9 F-16）。原本這裡把 client 的日期字串原封不動存進庫，而三份前端共用的那段
        推算在 UTC+8 會把「前一天」算成前兩天——修前端只治得了改得動的那一份，`app/`
        與 `frontend/` 已凍結，而下一個新寫的 client 還會再犯一次。

        沒帶 `event_date` 的回診（例如長輩用說的登記、或呼叫端只想設一顆）維持原路：
        後端沒有回診日就無從推算，收下 client 給的鬧鐘仍是唯一能做的事。
        """
        event_at = parse_event_at(body)
        if kind is not ScheduleKind.APPOINTMENT or event_at is None:
            return parse_occurrences(body.occurrences), event_at, []
        try:
            reminders = build_appointment_reminders(
                event_at=event_at, hour=appointment_hour, now=clock()
            )
        except TimeParseError as exc:
            # 走 A-01 的兩件式：code 給機器分支，message 用已經寫好的繁中人話。
            # 這條路徑的 TimeParseError 只會是「提醒時間全過了」——日期格式在
            # `parse_event_at` 就先擋掉了，不會混進來。
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.INVALID_SCHEDULE, "message": str(exc)},
            ) from exc
        warnings = (
            [appointment_day_before_skipped_text(appointment_hour)]
            if reminders.is_day_before_skipped
            else []
        )
        return reminders.occurrences, event_at, warnings

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
        occurrences, event_at, warnings = plan(body, kind)
        try:
            rows = schedules.create(
                elder_id=elder_id,
                kind=kind,
                title=body.title,
                # 走這支 API 的一律是家屬——長輩沒有 App 帳號可以打這裡。
                created_by=CreatedBy.GUARDIAN,
                occurrences=occurrences,
                event_at=event_at,
            )
        except ScheduleValidationError as exc:
            # code 給機器判斷、message 用服務層已經寫好的繁中人話（A-01，2026-07-29）。
            # 原本 detail=str(exc) 把整句中文塞進 error.code，前端無從分支；而那些句子
            # 是寫給長輩看的（LINE 流程與 LLM 工具都直接用），不能為了 code 而改掉。
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.INVALID_SCHEDULE, "message": str(exc)},
            ) from exc
        return ok(_group_json(find_group(elder_id, rows[0].group_id)), meta=_meta(warnings))

    @router.put("/elders/{elder_id}/schedules/{group_id}")
    def update_schedule(
        elder_id: str,
        group_id: str,
        body: ScheduleIn,
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        group = find_group(elder_id, group_id)  # 不屬於這位長輩就 404，不洩漏他人資料
        # 類型不可改（A-09，2026-07-29）。⚠️ `replace_group` 沿用原本的 kind 是**刻意的**
        # （見其 docstring：改內容不該讓家屬設的藥變成長輩設的、用藥變成回診），所以正解
        # 不是讓它可改。真正的缺陷是契約說謊——`kind` 是必填卻永遠被忽略，家屬把用藥改成
        # 回診會拿到 200 OK 與一筆完全沒變的資料，UI 沒有任何理由懷疑它。明確擋下來，
        # 呼叫端才知道要改類型得刪掉重建。
        if parse_kind(body.kind) is not group.kind:
            raise HTTPException(status_code=400, detail=ErrorCode.KIND_NOT_CHANGEABLE)
        occurrences, event_at, warnings = plan(body, group.kind)
        try:
            schedules.replace_group(
                group_id,
                title=body.title,
                occurrences=occurrences,
                event_at=event_at,
            )
        except ScheduleValidationError as exc:
            # code 給機器判斷、message 用服務層已經寫好的繁中人話（A-01，2026-07-29）。
            # 原本 detail=str(exc) 把整句中文塞進 error.code，前端無從分支；而那些句子
            # 是寫給長輩看的（LINE 流程與 LLM 工具都直接用），不能為了 code 而改掉。
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.INVALID_SCHEDULE, "message": str(exc)},
            ) from exc
        return ok(_group_json(find_group(elder_id, group_id)), meta=_meta(warnings))

    @router.delete("/elders/{elder_id}/schedules/{group_id}", status_code=204)
    def delete_schedule(
        elder_id: str, group_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> None:
        scope.assert_manages(auth, elder_id)
        find_group(elder_id, group_id)
        # 家屬可以取消長輩自己設的（反向才禁止），故 requested_by 固定為 GUARDIAN。
        schedules.cancel_group(group_id, requested_by=CreatedBy.GUARDIAN)

    return router
