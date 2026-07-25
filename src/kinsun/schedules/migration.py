"""既有用藥／回診資料遷入 schedules（統一排程 P2）。

**冪等靠決定性主鍵，不靠「先查再寫」**：`schedule_id` 由原主鍵推導（如
`{medication_id}-morning`），插入用 `ON CONFLICT DO NOTHING`。先查再寫有 TOCTOU
競態——webhook 與 scheduler 可能同時啟動、同時遷移；而且重跑時**不可**沿用
`PgScheduleStore.save` 的 upsert 語意，否則會把家屬事後在新表上做的修改整個蓋回
遷移當下的值。

價值定位（Leo 2026-07-25 確認庫內僅測試資料）：這支程式不是為了保護正式資料，而是
讓七位組員的個人庫在部署時自行癒合、不必手動重建測試場景。故失敗只記 ERROR、不阻斷
啟動——為了不存在的正式資料把整個服務擋下來並不划算。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from kinsun.db import Database
from kinsun.schedules.models import Audience, CreatedBy, RepeatKind, ScheduleKind

logger = logging.getLogger("kinsun.schedules.migration")

_INSERT = (
    "INSERT INTO schedules (schedule_id, group_id, elder_id, kind, title, repeat_kind, "
    "scheduled_at, repeat_time, repeat_weekday, event_at, audience, created_by, created_at, "
    "cancelled_at, settled_at, fired_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL) "
    "ON CONFLICT (schedule_id) DO NOTHING"
)


def _at(date_text: str, hour: int, minute: int, tz) -> float:
    year, month, day = (int(part) for part in date_text.split("-"))
    return datetime(year, month, day, hour, minute, tzinfo=tz).timestamp()


def backfill_from_legacy(
    db: Database,
    *,
    slot_hours: dict[str, int],
    appointment_hour: int,
    clock: Callable[[], datetime],
) -> int:
    """把 medications／appointments 遷入 schedules，回傳**真正新插入**的列數。可重跑。

    數字取自前後計數的差值，而不是累加「呼叫了幾次 INSERT」：後者在重跑時會回報
    與首次相同的數字，但實際上 ON CONFLICT DO NOTHING 讓一列都沒進去——一個會說謊
    的數字比沒有數字更糟，值班的人會以為遷移又跑了一遍。
    """
    now = clock()
    created_at = now.timestamp()
    before = db.query("SELECT count(*) FROM schedules")[0][0]

    for medication_id, elder_id, name, slots in db.query(
        "SELECT medication_id, elder_id, name, slots FROM medications"
    ):
        for slot in (s.strip() for s in slots.split(",")):
            hour = slot_hours.get(slot)
            if hour is None:
                logger.warning("用藥時段無對應鐘點，略過：%s（%s）", medication_id, slot)
                continue
            db.execute(
                _INSERT,
                (
                    f"{medication_id}-{slot}",
                    medication_id,
                    elder_id,
                    ScheduleKind.MEDICATION.value,
                    name,
                    RepeatKind.DAILY.value,
                    None,
                    f"{hour:02d}:00",
                    None,
                    None,
                    Audience.ELDER.value,
                    CreatedBy.GUARDIAN.value,
                    created_at,
                ),
            )

    today = now.date().isoformat()
    for appointment_id, elder_id, date_text, label, time_text in db.query(
        "SELECT appointment_id, elder_id, date, label, time FROM appointments WHERE date >= %s",
        (today,),
    ):
        # event_at 一律存日期；未指定看診時刻就落在當日 00:00（該約定見 jobs._event_time）。
        event_hour, event_minute = (0, 0)
        if time_text:
            event_hour, event_minute = (int(part) for part in time_text.split(":"))
        event_at = _at(date_text, event_hour, event_minute, now.tzinfo)
        # 一筆回診兩個鬧鐘：當天與前一天，皆在既有的 APPOINTMENT_REMINDER_HOUR 發出，
        # 與舊 job「今明兩窗、每筆提醒兩次」的行為一字不差。
        for offset in (0, 1):
            day = (
                datetime.fromtimestamp(event_at, now.tzinfo).date() - timedelta(days=offset)
            ).isoformat()
            db.execute(
                _INSERT,
                (
                    f"{appointment_id}-{offset}",
                    appointment_id,
                    elder_id,
                    ScheduleKind.APPOINTMENT.value,
                    label,
                    RepeatKind.ONCE.value,
                    _at(day, appointment_hour, 0, now.tzinfo),
                    "",
                    None,
                    event_at,
                    Audience.ELDER_AND_GUARDIAN.value,
                    CreatedBy.GUARDIAN.value,
                    created_at,
                ),
            )

    return db.query("SELECT count(*) FROM schedules")[0][0] - before
