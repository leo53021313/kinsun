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

_WEEKDAYS = "一二三四五六日"


class ScheduleFacts:
    """facts(elder_id) -> FactSection | None（該 kind 無排程回 None）。

    一個 kind 一個實例，由組裝根註冊三次。以 `group_id` 收斂：同一件事的多個鬧鐘
    （早晚兩次的藥、前一天加當天的回診）注入時必須合成一行，否則模型會以為那是
    兩種藥、兩次回診。
    """

    def __init__(
        self,
        store: ScheduleStore,
        *,
        kind: ScheduleKind,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._kind = kind
        self._clock = clock

    def facts(self, elder_id: str) -> FactSection | None:
        rows = [s for s in self._store.list_for_elder(elder_id) if s.kind == self._kind]
        if not rows:
            return None
        groups: dict[str, list[Schedule]] = {}
        for row in rows:
            groups.setdefault(row.group_id, []).append(row)
        items = [self._line(group) for group in groups.values()]
        return FactSection(_TITLES[self._kind], items)

    def _line(self, group: list[Schedule]) -> str:
        first = group[0]
        if self._kind == ScheduleKind.MEDICATION:
            labels = "、".join(slot_label(int(s.repeat_time[:2])) for s in group if s.repeat_time)
            return f"{first.title}（{labels}）"
        tz = self._clock().tzinfo
        if self._kind == ScheduleKind.APPOINTMENT:
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
