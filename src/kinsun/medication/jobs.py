"""用藥提醒的時段排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.medication.models import SLOT_LABELS, Medication, MedicationSlot
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
    cron = f"{minute} {hour} * * *"
    label = SLOT_LABELS[slot]

    def run() -> None:
        by_elder: dict[str, list[str]] = {}
        for med in meds_at_slot():
            by_elder.setdefault(med.elder_id, []).append(med.name)
        for elder_id, names in by_elder.items():
            try:
                elder = lookup_elder(elder_id)
                if elder is None or not elder.line_user_id:
                    continue
                if not is_consented(elder.line_user_id):
                    continue
                push(elder.line_user_id, f"{elder.name}，{label}該吃藥囉：{'、'.join(names)}")
            except Exception:  # noqa: BLE001 - 單一長輩失敗不影響其他
                logger.exception("用藥提醒失敗 elder=%s", elder_id)

    return Job(name=name, cron=cron, run=run)
