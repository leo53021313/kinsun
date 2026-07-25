"""舊表（medications／appointments）→ schedules 的過渡期對帳橋接。

**這是拋棄式程式碼，P3 換掉寫入端當天就刪。** 檔名如此命名正是為了讓人一眼看出
它不是長期資產。

存在的理由：P2 把排程器改成讀 `schedules`，但家屬的寫入端（LINE 選單、REST API）
還在寫舊表。少了對帳，P2 上線後家屬新增的藥不會提醒、刪掉的藥還會繼續提醒——
切片的目的是每一刀都能獨立運作，這個洞會讓 P2 做不到。

**過渡期舊表是唯一真相**，故對帳是 upsert ＋ 取消孤兒，而不是「只補不動」：
- 舊表有、新表沒有 → 寫進去。
- 兩邊都有但內容改了（改藥名、改時段、改回診日期）→ 蓋成舊表的值。
- 新表有、舊表沒有（家屬刪掉了）→ 取消。

三條邊界，少一條就會有一種操作在過渡期無聲失效。

upsert **只蓋內容欄**（title／repeat_time／scheduled_at／event_at／audience），
絕不碰 `fired_at`／`settled_at`／`created_at`——把 `fired_at` 洗掉會讓今天已經送過
的藥在同一天再送一次，正是「寧可漏、不可轟炸」要防的事。

作用範圍嚴格限縮在 `created_by='guardian'` 且 `kind ∈ (medication, appointment)`：
長輩用說的建的排程（P4）不歸舊表管，絕不能被對帳掃到而取消。

價值定位（Leo 2026-07-25 確認庫內僅測試資料）：對帳不是為了保護正式資料，而是讓
過渡期的家屬操作真的生效、並讓組員的個人庫自行癒合。故失敗只記 ERROR、不阻斷啟動。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from kinsun.db import Database
from kinsun.scheduler.scheduler import Job
from kinsun.schedules.models import Audience, CreatedBy, RepeatKind, ScheduleKind

logger = logging.getLogger("kinsun.schedules.legacy_bridge")

# 每五分鐘對一次帳。不做成每分鐘：對帳是全庫掃描，而家屬在 LINE 上改設定之後
# 最多等五分鐘才生效是可以接受的；派送 job 本身仍是每分鐘。
_RECONCILE_CRON = "*/5 * * * *"

_UPSERT = (
    "INSERT INTO schedules (schedule_id, group_id, elder_id, kind, title, repeat_kind, "
    "scheduled_at, repeat_time, repeat_weekday, event_at, audience, created_by, created_at, "
    "cancelled_at, settled_at, fired_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL) "
    "ON CONFLICT (schedule_id) DO UPDATE SET "
    "title = EXCLUDED.title, repeat_time = EXCLUDED.repeat_time, "
    "scheduled_at = EXCLUDED.scheduled_at, event_at = EXCLUDED.event_at, "
    "audience = EXCLUDED.audience"
)

# 對帳的作用範圍。長輩用說的建的排程不歸舊表管，不可被掃到。
# 也排除已結案的列：過期回診的鬧鐘早已 settled，不該因為舊表查不到它而被標成取消。
_SCOPE = "created_by = %s AND kind IN (%s, %s) AND cancelled_at IS NULL AND settled_at IS NULL"
_SCOPE_PARAMS = (
    CreatedBy.GUARDIAN.value,
    ScheduleKind.MEDICATION.value,
    ScheduleKind.APPOINTMENT.value,
)


def _at(date_text: str, hour: int, minute: int, tz) -> float:
    year, month, day = (int(part) for part in date_text.split("-"))
    return datetime(year, month, day, hour, minute, tzinfo=tz).timestamp()


def _desired_medications(db: Database, slot_hours: dict[str, int], created_at: float) -> dict:
    rows: dict[str, tuple] = {}
    for medication_id, elder_id, name, slots in db.query(
        "SELECT medication_id, elder_id, name, slots FROM medications"
    ):
        for slot in (s.strip() for s in slots.split(",")):
            hour = slot_hours.get(slot)
            if hour is None:
                logger.warning("用藥時段無對應鐘點，略過：%s（%s）", medication_id, slot)
                continue
            rows[f"{medication_id}-{slot}"] = (
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
            )
    return rows


def _desired_appointments(
    db: Database, appointment_hour: int, created_at: float, now: datetime
) -> dict:
    rows: dict[str, tuple] = {}
    for appointment_id, elder_id, date_text, label, time_text in db.query(
        "SELECT appointment_id, elder_id, date, label, time FROM appointments WHERE date >= %s",
        (now.date().isoformat(),),
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
            rows[f"{appointment_id}-{offset}"] = (
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
            )
    return rows


def reconcile_from_legacy(
    db: Database,
    *,
    slot_hours: dict[str, int],
    appointment_hour: int,
    clock: Callable[[], datetime],
) -> tuple[int, int]:
    """讓 schedules 反映舊表現況。回傳（寫入的列數, 取消的列數）。可重跑。"""
    now = clock()
    created_at = now.timestamp()
    desired = _desired_medications(db, slot_hours, created_at)
    desired.update(_desired_appointments(db, appointment_hour, created_at, now))

    for values in desired.values():
        db.execute(_UPSERT, values)

    existing = {
        row[0]
        for row in db.query(f"SELECT schedule_id FROM schedules WHERE {_SCOPE}", _SCOPE_PARAMS)
    }
    orphans = sorted(existing - desired.keys())
    if orphans:
        # 家屬在舊表刪掉了：對應的鬧鐘必須跟著停，否則長輩會一直被提醒一件已經取消的事。
        db.execute(
            "UPDATE schedules SET cancelled_at = %s "
            "WHERE schedule_id = ANY(%s) AND cancelled_at IS NULL",
            (created_at, orphans),
        )
    return len(desired), len(orphans)


def build_legacy_reconcile_job(
    *,
    db: Database,
    slot_hours: dict[str, int],
    appointment_hour: int,
    clock: Callable[[], datetime],
    name: str = "schedule-legacy-reconcile",
) -> Job:
    """把對帳掛成排程 job。**P3 換掉寫入端當天連同本檔一起刪。**

    不走 fanout_job：對帳沒有「母體逐筆」的語意，它是一次全庫比對；包成 fanout
    只會讓 Opik 多出一個永遠只有一筆的假 root。失敗由 Scheduler 的逐 job 隔離接住
    （記 exception 後其他 job 照跑），與「遷移失敗不阻斷」的定位一致。
    """

    def run() -> None:
        written, cancelled = reconcile_from_legacy(
            db,
            slot_hours=slot_hours,
            appointment_hour=appointment_hour,
            clock=clock,
        )
        if cancelled:
            logger.info("舊表對帳：寫入 %d 列、取消 %d 列", written, cancelled)

    return Job(name=name, cron=_RECONCILE_CRON, run=run)
