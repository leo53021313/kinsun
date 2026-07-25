"""把「日期＋時刻」換算成排程用的絕對時刻與 Occurrence。

三個入口（REST API、LINE 選單、長輩語音工具）都要做這件事。散在三處的下場是
時區處理各寫一版——其中一版忘了帶 tzinfo，於是那個入口建的提醒全部差八小時，
而且只有實際等到那個時間才會發現。故收斂到這裡，由呼叫端注入 clock。
"""

from __future__ import annotations

import re
from datetime import datetime

from kinsun.schedules.models import Occurrence, RepeatKind

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class TimeParseError(ValueError):
    """日期或時刻格式不合法。訊息為白話，可直接回給使用者。"""


def parse_epoch(date_text: str, time_text: str, *, now: datetime) -> float:
    """'2026-07-30' ＋ '10:30' → epoch 秒。時刻留空視為當日 00:00。

    00:00 對回診而言即「未指定看診時刻」（見 jobs._event_time 的約定）。
    """
    date_match = _DATE.match(date_text.strip())
    if not date_match:
        raise TimeParseError("日期要寫成 2026-07-30 這種格式。")
    hour, minute = 0, 0
    cleaned_time = time_text.strip()
    if cleaned_time:
        time_match = _TIME.match(cleaned_time)
        if not time_match:
            raise TimeParseError("時刻要寫成 08:30 這種格式。")
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
    year, month, day = (int(g) for g in date_match.groups())
    return datetime(year, month, day, hour, minute, tzinfo=now.tzinfo).timestamp()


def build_occurrence(
    *,
    repeat: str,
    time_text: str = "",
    date_text: str = "",
    weekday: int | None = None,
    now: datetime,
) -> Occurrence:
    """依 repeat 型別組出一個鬧鐘。格式錯誤一律拋 TimeParseError（白話訊息）。"""
    try:
        kind = RepeatKind(repeat)
    except ValueError as exc:
        raise TimeParseError("提醒方式只能是一次、每天或每週。") from exc
    if kind == RepeatKind.ONCE:
        return Occurrence(kind, scheduled_at=parse_epoch(date_text, time_text, now=now))
    cleaned = time_text.strip()
    if not _TIME.match(cleaned):
        raise TimeParseError("時刻要寫成 08:30 這種格式。")
    if kind == RepeatKind.WEEKLY:
        if weekday is None or not 0 <= weekday <= 6:
            raise TimeParseError("每週提醒要說是星期幾（0 是星期一）。")
        return Occurrence(kind, repeat_time=cleaned, repeat_weekday=weekday)
    return Occurrence(kind, repeat_time=cleaned)
