"""回診提醒的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Appointment:
    appointment_id: str
    elder_id: str
    date: str  # ISO "YYYY-MM-DD"
    label: str  # 自由文字，例「上午10點 心臟科回診 林口長庚」
