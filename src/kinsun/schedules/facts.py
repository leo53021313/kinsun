"""排程事實提供者：把長輩的排程注入對話情境的一段（FactSection）。

取代 `MedicationFacts` 與 `AppointmentFacts`，並多一段長輩自己交代的事。三種 kind
各成一段（而不是併成一大段）：段落標題本身就在告訴模型「這是藥」「這是回診」，
併起來等於把分類資訊丟掉，而模型對藥和對行程的講法本來就該不一樣。

用藥與回診兩段的標題**逐字沿用舊 facts**。那兩段字已經在正式 prompt 裡跑了很久，
換模組不是改措辭的時機——這個專案已經有過「注入什麼、模型就傾向講什麼」的教訓
（見 locations/facts.py 與 clock.py 的註解）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.memory.models import FactSection
from kinsun.schedules.models import RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import ScheduleStore
from kinsun.schedules.wording import slot_label

_TITLES = {
    ScheduleKind.MEDICATION: (
        "\n這位長者目前固定服用的藥（系統設定的提醒時段，僅供參考、非醫療指示）：\n"
    ),
    ScheduleKind.APPOINTMENT: "\n這位長者即將到來的回診（系統設定，僅供參考）：\n",
    ScheduleKind.CUSTOM: "\n這位長者自己交代要提醒的事：\n",
}

# 段落順序是 prompt 契約：與先前「註冊三個實例」的順序相同（見 composition）。
# 不靠 _TITLES 的 dict 插入序，明著寫出來才不會被無意的重排改掉。
_KIND_ORDER = (ScheduleKind.MEDICATION, ScheduleKind.APPOINTMENT, ScheduleKind.CUSTOM)

_WEEKDAYS = "一二三四五六日"


class ScheduleFacts:
    """facts(elder_id) -> list[FactSection]（三種 kind 各一段，無排程的 kind 不出現）。

    **一次查詢供三段**：三種 kind 的資料來自同一個 `list_for_elder(elder_id)`，
    先前一個 kind 一個實例、各打一次完全相同的查詢，三次跨海往返只是白等
    （單次往返實測約 250ms，2026-08-07）。段落仍維持三段獨立——標題本身就在
    告訴模型「這是藥」「這是回診」，併起來等於把分類資訊丟掉。

    以 `group_id` 收斂：同一件事的多個鬧鐘（早晚兩次的藥、前一天加當天的回診）
    注入時必須合成一行，否則模型會以為那是兩種藥、兩次回診。
    """

    def __init__(self, store: ScheduleStore, *, clock: Callable[[], datetime]) -> None:
        self._store = store
        self._clock = clock

    def facts(self, elder_id: str) -> list[FactSection]:
        rows = self._store.list_for_elder(elder_id)
        sections = []
        for kind in _KIND_ORDER:
            section = self._section(kind, rows)
            if section is not None:
                sections.append(section)
        return sections

    def _section(self, kind: ScheduleKind, rows: list[Schedule]) -> FactSection | None:
        matched = [s for s in rows if s.kind == kind]
        if not matched:
            return None
        groups: dict[str, list[Schedule]] = {}
        for row in matched:
            groups.setdefault(row.group_id, []).append(row)
        items = [self._line(kind, group) for group in groups.values()]
        return FactSection(_TITLES[kind], items)

    def _line(self, kind: ScheduleKind, group: list[Schedule]) -> str:
        first = group[0]
        if kind == ScheduleKind.MEDICATION:
            labels = "、".join(slot_label(int(s.repeat_time[:2])) for s in group if s.repeat_time)
            return f"{first.title}（{labels}）"
        tz = self._clock().tzinfo
        if kind == ScheduleKind.APPOINTMENT:
            when = first.event_at if first.event_at is not None else first.scheduled_at
            date = datetime.fromtimestamp(when, tz).date().isoformat() if when else ""
            return f"{date} {first.title}".strip()
        return f"{self._when_phrase(first, tz)} {first.title}".strip()

    def _when_phrase(self, schedule: Schedule, tz) -> str:
        if schedule.repeat_kind == RepeatKind.DAILY:
            return f"每天 {schedule.repeat_time}"
        if schedule.repeat_kind == RepeatKind.WEEKLY:
            index = schedule.repeat_weekday
            weekday = _WEEKDAYS[index] if index is not None else ""
            return f"每週{weekday} {schedule.repeat_time}"
        when = schedule.event_at if schedule.event_at is not None else schedule.scheduled_at
        if when is None:
            return ""
        moment = datetime.fromtimestamp(when, tz)
        return f"{moment.month}月{moment.day}日 {moment.strftime('%H:%M')}"
