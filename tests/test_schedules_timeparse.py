"""日期／時刻解析：三個入口共用的一份時區處理。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.schedules.models import RepeatKind
from kinsun.schedules.timeparse import TimeParseError, build_occurrence, parse_epoch

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
