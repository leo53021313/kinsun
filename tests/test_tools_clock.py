from datetime import datetime, timedelta, timezone

from kinsun.tools.clock import CURRENT_TIME_SPEC, build_current_time_handler

_TZ = timezone(timedelta(hours=8))


def _fixed(dt: datetime):
    return lambda: dt


def test_current_time_spec_name():
    assert CURRENT_TIME_SPEC.name == "get_current_time"


def test_current_time_spec_no_params():
    assert CURRENT_TIME_SPEC.parameters == {"type": "object", "properties": {}}


def test_handler_formats_afternoon():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 14, 30, tzinfo=_TZ)))({})
    assert "2026年7月3日" in out
    assert "星期五" in out  # 2026-07-03 為星期五
    assert "下午2點30分" in out


def test_handler_noon_on_the_hour():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 12, 0, tzinfo=_TZ)))({})
    assert "中午12點整" in out


def test_handler_morning_single_digit_minute():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 9, 5, tzinfo=_TZ)))({})
    assert "上午9點5分" in out


def test_handler_midnight_is_before_dawn():
    out = build_current_time_handler(_fixed(datetime(2026, 7, 3, 0, 15, tzinfo=_TZ)))({})
    assert "凌晨12點15分" in out
