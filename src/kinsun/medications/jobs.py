"""用藥提醒的時段排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.accounts.models import PrincipalType
from kinsun.channels.router import ChannelRouter
from kinsun.medications.models import SLOT_LABELS, Medication, MedicationSlot
from kinsun.reports.reminders import safe_record
from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.medications")


def build_medication_slot_job(
    *,
    slot: MedicationSlot,
    meds_at_slot: Callable[[], list[Medication]],
    lookup_elder: Callable[[str], object],
    has_valid_consent: Callable[[str], bool],
    router: ChannelRouter,
    hour: int,
    minute: int = 0,
    name: str,
    record: Callable[[str, str, str], None] | None = None,
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
        if elder is None or not has_valid_consent(elder_id):
            return
        sent = router.send_text(
            PrincipalType.ELDER, elder_id, f"{elder.name}，{label}該吃藥囉：{'、'.join(names)}"
        )
        if sent == 0:
            return  # 無任何綁定通道：不送也不記
        safe_record(record, elder_id, "medication", f"{label}用藥：{'、'.join(names)}")

    return fanout_job(
        name=name,
        hour=hour,
        minute=minute,
        population=population,
        action=action,
        item_id=lambda item: item[0],
        logger=logger,
    )
