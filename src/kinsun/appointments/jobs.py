"""回診提醒的每日排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.accounts.models import ElderGuardian, PrincipalType
from kinsun.appointments.models import Appointment
from kinsun.channels.router import ChannelRouter
from kinsun.reports.reminders import safe_record
from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.appointments")


def build_appointment_reminder_job(
    *,
    appts_on: Callable[[str], list[Appointment]],
    today: Callable[[], str],
    tomorrow: Callable[[], str],
    lookup_elder: Callable[[str], object],
    guardians_of: Callable[[str], list[ElderGuardian]],
    router: ChannelRouter,
    hour: int,
    minute: int = 0,
    name: str = "appointment-reminder",
    record: Callable[[str, str, str], None] | None = None,
) -> Job:
    def population() -> list[tuple[Appointment, str]]:
        items = [(a, "today") for a in appts_on(today())]
        items += [(a, "tomorrow") for a in appts_on(tomorrow())]
        return items

    def action(item: tuple[Appointment, str]) -> None:
        appt, when = item
        elder = lookup_elder(appt.elder_id)
        if elder is None:
            return
        when_word = "今天" if when == "today" else "明天"
        # 出站不查同意（✅ D-30 己-1）：長輩提醒一律照發。
        sent = router.send_text(
            PrincipalType.ELDER,
            appt.elder_id,
            f"{elder.name}，{when_word}要回診囉：{appt.label}。記得準時，需要的話請家人陪您去。",
        )
        # 家屬通知不受長輩可達性影響——收到可口頭轉告。
        for eg in guardians_of(appt.elder_id):
            router.send_text(
                PrincipalType.GUARDIAN,
                eg.guardian_id,
                f"【金孫提醒】{elder.name} {when_word}要回診——{appt.label}。",
            )
        if sent == 0:
            return  # 長輩無任何綁定通道：不記，否則健康報告顯示沒收到的提醒（✅ 庚-14）
        safe_record(record, appt.elder_id, "appointment", f"{when_word}回診：{appt.label}")

    return fanout_job(
        name=name,
        hour=hour,
        minute=minute,
        population=population,
        action=action,
        item_id=lambda item: item[0].appointment_id,
        logger=logger,
    )
