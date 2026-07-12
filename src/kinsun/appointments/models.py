"""回診提醒的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Appointment:
    appointment_id: str
    elder_id: str
    date: str  # ISO "YYYY-MM-DD"
    label: str  # 自由文字，例「心臟科回診 林口長庚」
    time: str = ""  # 看診時刻 ISO "HH:MM"（✅ 庚-15，選填；空＝未指定，提醒不帶時間）
