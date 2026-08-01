"""日期／時刻解析：三個入口共用的一份時區處理。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.models import RepeatKind
from kinsun.schedules.timeparse import (
    TimeParseError,
    build_appointment_reminders,
    build_occurrence,
    parse_epoch,
)

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 7, 25, 20, 0, tzinfo=TZ)


def test_parse_epoch_uses_the_caller_timezone():
    # 時區沒帶進來的話整批提醒會差八小時，而且要等到那個時刻才發現。
    assert (
        parse_epoch("2026-07-30", "10:30", now=NOW)
        == datetime(2026, 7, 30, 10, 30, tzinfo=TZ).timestamp()
    )


def test_parse_epoch_treats_blank_time_as_midnight():
    # 00:00 對回診而言即「未指定看診時刻」。
    assert (
        parse_epoch("2026-07-30", "", now=NOW) == datetime(2026, 7, 30, 0, 0, tzinfo=TZ).timestamp()
    )


@pytest.mark.parametrize("bad", ["2026/07/30", "26-07-30", "2026-7-30", "明天", ""])
def test_parse_epoch_rejects_malformed_dates(bad):
    with pytest.raises(TimeParseError, match="日期"):
        parse_epoch(bad, "10:30", now=NOW)


@pytest.mark.parametrize("bad", ["25:00", "8:30", "10.30", "晚上八點"])
def test_parse_epoch_rejects_malformed_times(bad):
    with pytest.raises(TimeParseError, match="時刻"):
        parse_epoch("2026-07-30", bad, now=NOW)


def test_build_once_occurrence():
    occurrence = build_occurrence(repeat="once", date_text="2026-07-30", time_text="20:45", now=NOW)
    assert occurrence.repeat_kind == RepeatKind.ONCE
    assert occurrence.scheduled_at == datetime(2026, 7, 30, 20, 45, tzinfo=TZ).timestamp()


def test_build_daily_occurrence():
    occurrence = build_occurrence(repeat="daily", time_text="08:00", now=NOW)
    assert occurrence.repeat_kind == RepeatKind.DAILY
    assert occurrence.repeat_time == "08:00"
    assert occurrence.scheduled_at is None


def test_build_weekly_occurrence():
    occurrence = build_occurrence(repeat="weekly", time_text="15:00", weekday=2, now=NOW)
    assert occurrence.repeat_weekday == 2


def test_weekly_without_weekday_is_rejected():
    with pytest.raises(TimeParseError, match="星期"):
        build_occurrence(repeat="weekly", time_text="15:00", now=NOW)


@pytest.mark.parametrize("weekday", [-1, 7, 99])
def test_weekly_rejects_out_of_range_weekday(weekday):
    with pytest.raises(TimeParseError, match="星期"):
        build_occurrence(repeat="weekly", time_text="15:00", weekday=weekday, now=NOW)


def test_unknown_repeat_is_rejected():
    with pytest.raises(TimeParseError, match="一次"):
        build_occurrence(repeat="yearly", time_text="15:00", now=NOW)


# ── 回診的兩顆鬧鐘（12 §9 F-16 的修法） ──
#
# ⚠️ 下面每一條都把 `Asia/Taipei` 釘進 `now` 與斷言，不讀執行機器的環境時區：
# 「前一天」算錯只發生在 UTC 以東，靠環境時區的測試在 UTC 的 CI 上會全綠。


def _at(year: int, month: int, day: int, hour: int) -> float:
    return datetime(year, month, day, hour, 0, tzinfo=TZ).timestamp()


def test_appointment_reminders_are_the_day_before_and_the_day_itself():
    reminders = build_appointment_reminders(
        event_at=parse_epoch("2026-08-05", "10:30", now=NOW), hour=8, now=NOW
    )
    assert [o.repeat_kind for o in reminders.occurrences] == [RepeatKind.ONCE, RepeatKind.ONCE]
    # 前一天＝2026-08-04。在 UTC+8 用 `toISOString()` 換算會得到 08-03（提早兩天響）。
    assert [o.scheduled_at for o in reminders.occurrences] == [
        _at(2026, 8, 4, 8),
        _at(2026, 8, 5, 8),
    ]
    assert reminders.is_day_before_skipped is False


def test_appointment_reminders_cross_the_month_boundary_correctly():
    """月初的回診，「前一天」要落在上個月的最後一天。"""
    reminders = build_appointment_reminders(
        event_at=parse_epoch("2026-09-01", "", now=NOW), hour=8, now=NOW
    )
    assert [o.scheduled_at for o in reminders.occurrences] == [
        _at(2026, 8, 31, 8),
        _at(2026, 9, 1, 8),
    ]


def test_appointment_reminders_use_the_configured_hour():
    reminders = build_appointment_reminders(
        event_at=parse_epoch("2026-08-05", "", now=NOW), hour=9, now=NOW
    )
    assert [o.scheduled_at for o in reminders.occurrences] == [
        _at(2026, 8, 4, 9),
        _at(2026, 8, 5, 9),
    ]


def test_day_before_that_has_already_passed_is_skipped_and_reported():
    """下午設明天的回診：前一天那顆＝今天早上，略過它並回報——你沒辦法提醒一個人昨天。"""
    afternoon = datetime(2026, 7, 25, 15, 0, tzinfo=TZ)
    reminders = build_appointment_reminders(
        event_at=parse_epoch("2026-07-26", "", now=afternoon), hour=8, now=afternoon
    )
    assert [o.scheduled_at for o in reminders.occurrences] == [_at(2026, 7, 26, 8)]
    assert reminders.is_day_before_skipped is True


def test_a_reminder_landing_exactly_on_now_counts_as_passed():
    """門檻與 `ScheduleService._validate` 同為 `<=`。

    留下一顆剛好等於此刻的鬧鐘，服務層下一瞬間仍會判它過期、整筆建不起來——那正是
    這裡要防的症狀，所以邊界必須同向。
    """
    eight_sharp = datetime(2026, 7, 25, 8, 0, tzinfo=TZ)
    reminders = build_appointment_reminders(
        event_at=parse_epoch("2026-07-26", "", now=eight_sharp), hour=8, now=eight_sharp
    )
    assert reminders.is_day_before_skipped is True
    assert [o.scheduled_at for o in reminders.occurrences] == [_at(2026, 7, 26, 8)]


def test_appointment_whose_reminders_have_all_passed_is_rejected():
    """今天下午設今天的回診：兩顆都過去了，話要講在回診日上——那才是家屬改得動的。"""
    afternoon = datetime(2026, 7, 25, 15, 0, tzinfo=TZ)
    with pytest.raises(TimeParseError, match="回診"):
        build_appointment_reminders(
            event_at=parse_epoch("2026-07-25", "", now=afternoon), hour=8, now=afternoon
        )
