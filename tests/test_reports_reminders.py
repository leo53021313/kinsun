"""提醒種類列舉：寫入端與讀取端共用的唯一清單。"""

from __future__ import annotations

from kinsun.reports.reminders import (
    REMINDER_KIND_APPOINTMENT,
    REMINDER_KIND_CUSTOM,
    REMINDER_KIND_MEDICATION,
    REMINDER_KIND_PROACTIVE_CARE,
    REMINDER_KIND_PROACTIVE_GREETING,
    REMINDER_KINDS,
)


def test_custom_is_a_known_reminder_kind():
    # 長輩用說的建的提醒送出後記這個 kind；健康報告與 admin 共用同一份列舉。
    assert REMINDER_KIND_CUSTOM == "custom"
    assert REMINDER_KIND_CUSTOM in REMINDER_KINDS


def test_every_kind_constant_is_listed():
    # 常數與列舉不同步是這張表最容易出的錯：新增常數卻忘了加進 REMINDER_KINDS。
    assert set(REMINDER_KINDS) == {
        REMINDER_KIND_MEDICATION,
        REMINDER_KIND_APPOINTMENT,
        REMINDER_KIND_CUSTOM,
        REMINDER_KIND_PROACTIVE_GREETING,
        REMINDER_KIND_PROACTIVE_CARE,
    }


def test_schedule_kinds_and_reminder_kinds_agree():
    """`ScheduleKind` 的三個字面值必須就是 reminder_logs 的三種 kind。

    派送 job 直接拿 `schedule.kind` 當 `reminder_logs.kind` 寫入，兩邊一旦漂移，
    健康報告會統計到一個不存在的種類，而型別檢查不會攔——只能靠這條測試。
    """
    from kinsun.schedules.models import ScheduleKind

    assert {k.value for k in ScheduleKind} <= set(REMINDER_KINDS)
