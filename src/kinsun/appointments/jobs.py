"""回診提醒的每日排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.appointments.models import Appointment
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
    is_consented: Callable[[str], bool],
    guardian_line_ids: Callable[[str], list[str]],
    push: Callable[[str, str], None],
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
        if elder.line_user_id and is_consented(elder.line_user_id):
            push(
                elder.line_user_id,
                f"{elder.name}，{when_word}要回診囉：{appt.label}。記得準時，需要的話請家人陪您去。",
            )
        for line_id in guardian_line_ids(appt.elder_id):
            push(line_id, f"【金孫提醒】{elder.name} {when_word}要回診——{appt.label}。")
        safe_record(record, appt.elder_id, "appointment", f"{when_word}回診：{appt.label}")

    return fanout_job(
        name=name,
        hour=hour,
        minute=minute,
        population=population,
        action=action,
        item_id=lambda item: item[0].appt_id,
        logger=logger,
    )
