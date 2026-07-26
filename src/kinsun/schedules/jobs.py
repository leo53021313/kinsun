"""統一排程的派送 job：每分鐘掃一次，把到期的鬧鐘送出去。

取代原本四個用藥 job（每日固定時段）＋一個回診 job（每日掃今明兩窗）。頻率之所以
必須提高到每分鐘，是因為時刻改成每位長輩、每筆排程各自設定——沒有共用的鐘點可以
掛 cron 了。

**判定窗不是補發窗**（決策 8「過期就不發」）：`scheduled_at` 是秒級、掃描是分鐘級，
沒有容許量的話每一則提醒都會晚到最多一分鐘、甚至因 tick 漂移整筆漏掉。窗只吸收這個
抖動；伺服器停機超過窗，那筆就是作廢、不補。

過期的一次性排程**必須結案**（寫 `settled_at`）而不能只是跳過，否則每分鐘都會重複
撈到同一批殭屍列。但它並沒有真的送出，故不寫 `fired_at`——那欄的語意是「最後送出
時刻」，寫了就是說謊。

送出前先標記、後送出（at-most-once）：與問候 job 的帳本同向，也與舊 job 的語意一致
（舊 job 每天只跑一次，送失敗就是漏掉、不會重試）。標記失敗讓例外冒到 fanout ＝
跳過本輪、下一分鐘重試；送出失敗則該則提醒就此漏掉——**寧可漏，不可轟炸**。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from kinsun.accounts.models import ElderGuardian, PrincipalType
from kinsun.channels.router import ChannelRouter
from kinsun.reports.reminders import safe_record
from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job
from kinsun.schedules.models import Audience, RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import ScheduleStore
from kinsun.schedules.wording import appointment_texts, custom_text, medication_text

logger = logging.getLogger("kinsun.schedules")

_DISPATCH_CRON = "* * * * *"


@dataclass(frozen=True)
class _Batch:
    """一則要送出的訊息。用藥可含多筆（同一位長輩、同一個時段小時）。"""

    elder_id: str
    kind: ScheduleKind
    schedules: tuple[Schedule, ...]
    hour: int  # 用藥的時段詞由它推算

    @property
    def item_id(self) -> str:
        return self.schedules[0].schedule_id


def _window_minutes(now: datetime, window_seconds: int) -> tuple[str, ...]:
    """判定窗 (now - window, now] 涵蓋的每一個 HH:MM。

    重複型排程存的是分鐘級的 'HH:MM'，而窗是秒級的，故必須展開成一組分鐘值去比對；
    只比對當下那一分鐘，掃描稍有延遲就會整筆漏掉。
    """
    minutes = {now.strftime("%H:%M")}
    for offset in range(1, window_seconds // 60 + 1):
        minutes.add((now - timedelta(minutes=offset)).strftime("%H:%M"))
    return tuple(sorted(minutes))


def _day_start(now: datetime) -> float:
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _hour_of(schedule: Schedule, now: datetime) -> int:
    """該筆排程的提醒時刻是幾點——用藥的時段詞（早上／中午／晚上／睡前）由它決定。"""
    if schedule.repeat_time:
        return int(schedule.repeat_time[:2])
    if schedule.scheduled_at is not None:
        return datetime.fromtimestamp(schedule.scheduled_at, now.tzinfo).hour
    return now.hour


def _when_word(event_at: float, now: datetime) -> str:
    days = (datetime.fromtimestamp(event_at, now.tzinfo).date() - now.date()).days
    if days == 0:
        return "今天"
    if days == 1:
        return "明天"
    event = datetime.fromtimestamp(event_at, now.tzinfo)
    return f"{event.month}月{event.day}日"


def _event_time(event_at: float, now: datetime) -> str:
    """看診時刻的顯示字串；落在當日 00:00 ＝ 未指定時刻，回空字串。

    以 00:00 表示「未指定」是刻意的約定：回診的提醒時刻與事件時刻分屬兩欄，事件那欄
    若留 None 就算不出「今天／明天」（那正是回診話術的骨幹）。真實世界不存在午夜零時
    的回診，故拿它當哨兵值不會誤傷。庚-15 的舊語意（time 為空＝提醒不帶時間）因此保住。
    """
    event = datetime.fromtimestamp(event_at, now.tzinfo)
    if event.hour == 0 and event.minute == 0:
        return ""
    return event.strftime("%H:%M")


def _text_for(batch: _Batch, elder_name: str, now: datetime) -> tuple[str, str]:
    """回傳（長輩訊息, 家屬訊息）；家屬訊息為空字串＝不發家屬。"""
    if batch.kind == ScheduleKind.MEDICATION:
        titles = [s.title for s in batch.schedules]
        return medication_text(elder_name, batch.hour, titles), ""
    schedule = batch.schedules[0]
    if batch.kind == ScheduleKind.APPOINTMENT:
        event_at = schedule.event_at if schedule.event_at is not None else now.timestamp()
        return appointment_texts(
            elder_name, schedule.title, _when_word(event_at, now), _event_time(event_at, now)
        )
    minutes_ahead = 0
    if schedule.event_at is not None and schedule.scheduled_at is not None:
        minutes_ahead = max(0, round((schedule.event_at - schedule.scheduled_at) / 60))
    return custom_text(elder_name, schedule.title, minutes_ahead), ""


def build_schedule_dispatch_job(
    *,
    store: ScheduleStore,
    lookup_elder: Callable[[str], object],
    guardians_of: Callable[[str], list[ElderGuardian]],
    router: ChannelRouter,
    clock: Callable[[], datetime],
    window_seconds: int = 90,
    record: Callable[[str, str, str], None] | None = None,
    name: str = "schedule-dispatch",
) -> Job:
    def population() -> list[_Batch]:
        now = clock()
        window_start = now.timestamp() - window_seconds
        due: list[Schedule] = list(
            store.list_due_repeating(
                times=_window_minutes(now, window_seconds),
                weekday=now.weekday(),
                not_fired_since=_day_start(now),
            )
        )
        for schedule in store.list_due_once(until=now.timestamp()):
            if schedule.scheduled_at is not None and schedule.scheduled_at < window_start:
                # 過期作廢：結案但不送，也不記 fired_at。不結案的話它會在每一輪掃描
                # 被重複撈出來，成為永遠處理不完的殭屍列。
                store.mark_settled(schedule.schedule_id, now=now.timestamp())
                logger.info("排程過期未送（超出判定窗）：%s", schedule.schedule_id)
                continue
            due.append(schedule)
        return _aggregate(due, now)

    def _aggregate(due: list[Schedule], now: datetime) -> list[_Batch]:
        """用藥按（長輩＋時段小時）合併成一則（舊 job 的「多顆藥一則」行為）；其餘逐筆。"""
        merged: dict[tuple[str, int], list[Schedule]] = {}
        batches: list[_Batch] = []
        for schedule in due:
            hour = _hour_of(schedule, now)
            if schedule.kind == ScheduleKind.MEDICATION:
                merged.setdefault((schedule.elder_id, hour), []).append(schedule)
                continue
            batches.append(_Batch(schedule.elder_id, schedule.kind, (schedule,), hour))
        for (elder_id, hour), rows in merged.items():
            batches.append(_Batch(elder_id, ScheduleKind.MEDICATION, tuple(rows), hour))
        return batches

    def action(batch: _Batch) -> None:
        now = clock()
        # 出站不查同意（✅ D-30 己-1）：提醒一律照發；查無此長輩才略過。
        elder = lookup_elder(batch.elder_id)
        if elder is None:
            return
        # 先標記、後送出（at-most-once）：標記失敗讓例外冒到 fanout ＝ 跳過本輪重試；
        # 送出失敗則此則漏掉——與舊 job「每天只跑一次、送失敗就漏」的語意一致。
        for schedule in batch.schedules:
            store.mark_fired(schedule.schedule_id, now=now.timestamp())
            if schedule.repeat_kind == RepeatKind.ONCE:
                store.mark_settled(schedule.schedule_id, now=now.timestamp())

        elder_text, guardian_text = _text_for(batch, elder.name, now)
        sent = router.send_text(PrincipalType.ELDER, batch.elder_id, elder_text)
        if guardian_text and batch.schedules[0].audience == Audience.ELDER_AND_GUARDIAN:
            # 家屬通知不受長輩可達性影響——收到可口頭轉告（appointments/jobs.py 舊行為）。
            for eg in guardians_of(batch.elder_id):
                router.send_text(PrincipalType.GUARDIAN, eg.guardian_id, guardian_text)
        if sent == 0:
            return  # 長輩零通道送達：不記，否則健康報告顯示沒收到的提醒（✅ 庚-14）
        safe_record(record, batch.elder_id, batch.kind.value, elder_text)

    return fanout_job(
        name=name,
        cron=_DISPATCH_CRON,
        population=population,
        action=action,
        item_id=lambda batch: batch.item_id,
        # 遲到超過判定窗＝這段時間該送的提醒**已經永久遺失**（窗外的一律作廢不補，
        # 見上方 population）。後台的預設容許量 300 秒遠大於這個窗，會在提醒已經
        # 掉了的時候還顯示健康——那正是 2026-07-26 事故裡最該被看見卻沒被看見的一層。
        max_lateness_seconds=float(window_seconds),
        logger=logger,
    )
