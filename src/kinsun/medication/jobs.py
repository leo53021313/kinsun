"""用藥提醒的時段排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.medication.models import SLOT_LABELS, Medication, MedicationSlot
from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.medication")


def build_medication_slot_job(
    *,
    slot: MedicationSlot,
    meds_at_slot: Callable[[], list[Medication]],
    lookup_elder: Callable[[str], object],
    is_consented: Callable[[str], bool],
    push: Callable[[str, str], None],
    hour: int,
    minute: int = 0,
    name: str,
) -> Job:
    label = SLOT_LABELS[slot]

    def population() -> list[tuple[str, list[str]]]:
        by_elder: dict[str, list[str]] = {}
        for med in meds_at_slot():
            by_elder.setdefault(med.elder_id, []).append(med.name)
        return list(by_elder.items())

    def action(item: tuple[str, list[str]]) -> None:
        elder_id, names = item
        elder = lookup_elder(elder_id)
        if elder is None or not elder.line_user_id:
            return
        if not is_consented(elder.line_user_id):
            return
        push(elder.line_user_id, f"{elder.name}，{label}該吃藥囉：{'、'.join(names)}")

    return fanout_job(
        name=name,
        hour=hour,
        minute=minute,
        population=population,
        action=action,
        item_id=lambda item: item[0],
        logger=logger,
    )
