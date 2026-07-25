"""統一排程的資料模型。

一列 ＝ 一個鬧鐘，不是一件事（spec 2026-07-25-統一排程系統）。回診之所以前一天
與當天各響一次、用藥之所以早上與晚上各響一次，本質是同一件事有多個提醒時刻；
一列若硬要承載一件事，就得在欄位裡再長出一套提醒規則語法——複雜度只會搬家、
不會消失。同一件事的多個鬧鐘以 group_id 串起，家屬刪「這個藥」＝刪整組。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScheduleKind(StrEnum):
    """排程類別。字面值同時是 reminder_logs 的 kind，送出時直接沿用。"""

    MEDICATION = "medication"
    APPOINTMENT = "appointment"
    CUSTOM = "custom"


class RepeatKind(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class Audience(StrEnum):
    """收件對象。

    用列舉而非布林 notify_guardians：布林命名規範要求 is_／has_／can_ 前綴，硬套
    會得到 has_guardian_notice 這種彆扭名字；列舉也保留日後新增對象的空間。
    """

    ELDER = "elder"
    ELDER_AND_GUARDIAN = "elder_and_guardian"


class CreatedBy(StrEnum):
    ELDER = "elder"
    GUARDIAN = "guardian"


def audience_for(kind: ScheduleKind) -> Audience:
    """收件對象由 kind 決定、與誰建立無關。

    長輩自己用說的登記回診，家屬一樣收到——那正是家屬最想被告知的一類事。
    """
    if kind == ScheduleKind.APPOINTMENT:
        return Audience.ELDER_AND_GUARDIAN
    return Audience.ELDER


@dataclass(frozen=True)
class Occurrence:
    """建立排程時描述「一個鬧鐘」的輸入：一次性給 scheduled_at，重複型給 repeat_time。"""

    repeat_kind: RepeatKind
    scheduled_at: float | None = None
    repeat_time: str = ""  # 'HH:MM'
    repeat_weekday: int | None = None  # 0–6，週一＝0（同 datetime.weekday()）


@dataclass(frozen=True)
class Schedule:
    """一個鬧鐘。時刻一律 epoch 秒（DOUBLE PRECISION）。

    event_at 與提醒時刻分離是話術能活過來的關鍵：回診事件在 10:30、提醒在前一天
    九點，訊息才講得出「明天 10:30 要回診」。None ＝ 事件與提醒同刻。

    settled_at 與 fired_at 刻意分開：過期的一次性排程必須結案，否則每分鐘掃描都
    會重複撈到同一批殭屍列；但它並沒有真的送出，記成 fired_at 會讓「最後送出時刻」
    說謊。已送出者兩欄同寫，過期作廢者只寫 settled_at。
    """

    schedule_id: str
    group_id: str
    elder_id: str
    kind: ScheduleKind
    title: str
    repeat_kind: RepeatKind
    scheduled_at: float | None = None  # once 的提醒時刻；重複型為 None
    repeat_time: str = ""  # 重複型的 'HH:MM'
    repeat_weekday: int | None = None  # weekly 的 0–6
    event_at: float | None = None
    audience: Audience = Audience.ELDER
    created_by: CreatedBy = CreatedBy.GUARDIAN
    created_at: float = 0.0
    cancelled_at: float | None = None
    settled_at: float | None = None
    fired_at: float | None = None
