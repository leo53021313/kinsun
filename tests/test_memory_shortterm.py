from datetime import datetime, timedelta, timezone

from kinsun.memory.shortterm import previous_day_bounds

TPE = timezone(timedelta(hours=8))


def test_previous_day_bounds_is_the_completed_day_before_now():
    # 凌晨 3 點跑的整理批次，要整理「剛結束的那一天」(6/28 整天)，
    # 而不是當下這天才過幾小時的片段 (6/29 00:00–03:00)。
    now = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    start, end = previous_day_bounds(now)
    assert start == datetime(2026, 6, 28, 0, 0, tzinfo=TPE).timestamp()
    assert end == datetime(2026, 6, 29, 0, 0, tzinfo=TPE).timestamp()


def test_previous_day_bounds_excludes_today_and_day_before_yesterday():
    now = datetime(2026, 6, 29, 23, 30, tzinfo=TPE)
    start, end = previous_day_bounds(now)
    # 6/27 23:59 不算進來，6/28 任意時刻算，6/29 00:00 起不算
    assert datetime(2026, 6, 27, 23, 59, tzinfo=TPE).timestamp() < start
    assert start <= datetime(2026, 6, 28, 9, 0, tzinfo=TPE).timestamp() < end
    assert end <= datetime(2026, 6, 29, 0, 0, tzinfo=TPE).timestamp()
