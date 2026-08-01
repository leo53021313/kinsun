"""把「日期＋時刻」換算成排程用的絕對時刻與 Occurrence。

三個入口（REST API、LINE 選單、長輩語音工具）都要做這件事。散在三處的下場是
時區處理各寫一版——其中一版忘了帶 tzinfo，於是那個入口建的提醒全部差八小時，
而且只有實際等到那個時間才會發現。故收斂到這裡，由呼叫端注入 clock。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from kinsun.schedules.models import Occurrence, RepeatKind

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class TimeParseError(ValueError):
    """日期或時刻不合法：格式錯誤，或推算出來的提醒時刻全部已過。

    訊息為白話，可直接回給使用者。
    """


def parse_epoch(date_text: str, time_text: str, *, now: datetime) -> float:
    """'2026-07-30' ＋ '10:30' → epoch 秒。時刻留空視為當日 00:00。

    00:00 對回診而言即「未指定看診時刻」（見 jobs._event_time 的約定）。
    """
    date_match = _DATE.match(date_text.strip())
    if not date_match:
        # 範例日期跟著 now 走，不寫死：這句是回給模型的工具錯誤，它會照抄示範。
        # 2026-08-01 實測收到「要寫成 2026-07-30 這種格式」——一個已經過去的日子。
        raise TimeParseError(f"日期要寫成 {now:%Y-%m-%d} 這種格式。")
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


@dataclass(frozen=True)
class AppointmentReminders:
    """回診的一組提醒。`occurrences` 已經剔除掉時刻已過的那幾顆。

    `is_day_before_skipped` 是給呼叫端**拿去告訴家屬**的：少建一顆鬧鐘不可以靜默，
    家屬心裡設的是「前一天也會提醒」，這一次得由他自己開口。
    """

    occurrences: tuple[Occurrence, ...]
    is_day_before_skipped: bool


def build_appointment_reminders(
    *, event_at: float, hour: int, now: datetime
) -> AppointmentReminders:
    """回診固定兩顆鬧鐘（前一天與當天的 `hour` 點），日期由**後端**自己從回診日推算。

    ⚠️ **不採信 client 送來的「前一天」**（12 §9 F-16）：`app/`／`frontend/` 兩份前端
    以 `new Date("YYYY-MM-DDT00:00:00")`（依**本地時區**解析）減 24 小時、再用
    `toISOString()`（**UTC**）取日期字串。UTC+8 的本地午夜是前一天 16:00Z，於是
    「前一天」被多減一天——提醒提早**兩天**響，長輩白跑一趟。本模組檔頭寫的正是這件事
    （散在三處的時區處理必然各寫一版），故「前一天是哪一天」自此只有這一份答案。

    **時刻已過的那幾顆直接不建**——你沒辦法提醒一個人昨天。下午替明天的回診設提醒時，
    「前一天 `hour` 點」是今天早上，原本會讓服務層以「那個時間已經過去了」擋掉**整筆**
    排程（不是只少一顆），而家屬填的明明是明天。

    兩顆都過去了才拋錯，且訊息講的是**真正的原因**（提醒固定在那個鐘點），不是叫家屬
    去改一個沒錯的欄位：上午十點登記「今天下午三點」的回診時，回診日期完全正確，錯的
    是這個系統只在 `hour` 點提醒——叫他去確認日期，他會什麼都找不到然後再試一次。
    """
    event_day = datetime.fromtimestamp(event_at, now.tzinfo).date()
    current = now.timestamp()
    occurrences: list[Occurrence] = []
    is_day_before_skipped = False
    for days_before in (1, 0):
        day = event_day - timedelta(days=days_before)
        at = datetime(day.year, day.month, day.day, hour, 0, tzinfo=now.tzinfo).timestamp()
        # 門檻用 `<=` 與 `ScheduleService._validate` 對齊：留下一顆剛好等於此刻的鬧鐘，
        # 服務層下一瞬間仍會判它過期，整筆照樣建不起來——那正是這裡要防的症狀。
        if at <= current:
            if days_before == 1:
                is_day_before_skipped = True
            continue
        occurrences.append(Occurrence(RepeatKind.ONCE, scheduled_at=at))
    if not occurrences:
        stamp = f"{hour:02d}:00"
        raise TimeParseError(
            f"回診的提醒固定在前一天與當天的 {stamp}，這兩個時刻都已經過了。"
            "如果回診就在今天，請您直接跟長輩說一聲；不然請確認回診日期。"
        )
    return AppointmentReminders(tuple(occurrences), is_day_before_skipped)
