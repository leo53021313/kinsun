"""用藥提醒的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MedicationSlot(StrEnum):
    MORNING = "morning"
    NOON = "noon"
    EVENING = "evening"
    BEDTIME = "bedtime"


SLOT_ORDER = (
    MedicationSlot.MORNING,
    MedicationSlot.NOON,
    MedicationSlot.EVENING,
    MedicationSlot.BEDTIME,
)
SLOT_LABELS = {
    MedicationSlot.MORNING: "早上",
    MedicationSlot.NOON: "中午",
    MedicationSlot.EVENING: "晚上",
    MedicationSlot.BEDTIME: "睡前",
}


@dataclass(frozen=True)
class Medication:
    medication_id: str
    elder_id: str
    name: str
    slots: tuple[MedicationSlot, ...]


def slots_label(slots) -> str:
    return "、".join(SLOT_LABELS[s] for s in SLOT_ORDER if s in slots)
