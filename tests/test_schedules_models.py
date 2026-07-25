"""排程領域模型：列舉字面值與收件對象規則。"""

from __future__ import annotations

from kinsun.schedules.models import (
    Audience,
    CreatedBy,
    Occurrence,
    RepeatKind,
    Schedule,
    ScheduleKind,
    audience_for,
)


def test_kind_values_match_reminder_log_kinds():
    # 這三個字面值同時是 reminder_logs 的 kind（P2 送出時直接沿用），不可改。
    assert ScheduleKind.MEDICATION.value == "medication"
    assert ScheduleKind.APPOINTMENT.value == "appointment"
    assert ScheduleKind.CUSTOM.value == "custom"


def test_repeat_and_audience_and_created_by_values():
    assert [r.value for r in RepeatKind] == ["once", "daily", "weekly"]
    assert [a.value for a in Audience] == ["elder", "elder_and_guardian"]
    assert [c.value for c in CreatedBy] == ["elder", "guardian"]


def test_appointment_notifies_guardians_regardless_of_author():
    # 收件對象由 kind 決定、與誰建立無關：長輩自己用說的登記回診，家屬一樣該知道。
    assert audience_for(ScheduleKind.APPOINTMENT) == Audience.ELDER_AND_GUARDIAN


def test_other_kinds_notify_elder_only():
    assert audience_for(ScheduleKind.MEDICATION) == Audience.ELDER
    assert audience_for(ScheduleKind.CUSTOM) == Audience.ELDER


def test_schedule_defaults_are_inactive_markers():
    schedule = Schedule(
        schedule_id="s1",
        group_id="g1",
        elder_id="e1",
        kind=ScheduleKind.CUSTOM,
        title="去吃飯",
        repeat_kind=RepeatKind.ONCE,
        scheduled_at=100.0,
        created_at=1.0,
    )
    assert schedule.cancelled_at is None
    assert schedule.settled_at is None
    assert schedule.fired_at is None
    assert schedule.audience == Audience.ELDER
    assert schedule.created_by == CreatedBy.GUARDIAN


def test_occurrence_carries_one_alarm():
    once = Occurrence(RepeatKind.ONCE, scheduled_at=100.0)
    weekly = Occurrence(RepeatKind.WEEKLY, repeat_time="15:00", repeat_weekday=2)
    assert once.repeat_time == ""
    assert once.repeat_weekday is None
    assert weekly.scheduled_at is None
