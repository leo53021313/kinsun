"""提醒設定的引導式選單（被綁定流程委派，共用 session）。

取代 `MedicationMenu` 與 `AppointmentMenu` 兩個選單（D-76 P3 入口合一）。家屬只要
記住一個入口，用藥、回診與其他提醒都從這裡進去。

三種類型問的問題不同（藥問時段、回診問日期、其他問重複方式），但流程骨架相同：
選長輩 → 選類型 → 問名稱 → 問時間。差異全部收在 `_when_prompt` 與 `_parse_when`
這一對函式裡，新增第四種類型時只要改這兩處。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.binding.session import BindingSession, BindingSessionStore, BindingState
from kinsun.schedules.models import CreatedBy, Occurrence, RepeatKind, ScheduleKind
from kinsun.schedules.service import ScheduleService, ScheduleValidationError
from kinsun.schedules.timeparse import TimeParseError, build_appointment_reminders, parse_epoch
from kinsun.schedules.wording import appointment_day_before_skipped_text, slot_label

_MENU = "提醒設定：請回覆數字：\n1️⃣ 新增提醒\n2️⃣ 查看提醒\n3️⃣ 刪除提醒"
_KIND_PROMPT = "請問是哪一種？回覆數字：\n1️⃣ 吃藥\n2️⃣ 回診\n3️⃣ 其他"
_SLOT_PROMPT = (
    "請問什麼時候吃？回覆數字（可複選）：\n"
    "1 早上　2 中午　3 晚上　4 睡前\n"
    "（例如「1 3」表示早上和晚上；也可以直接回覆時刻，例如 07:30）"
)
_APPT_PROMPT = "請問哪一天回診？例如 2026-07-30；要指定看診時間就寫 2026-07-30 10:30。"
_CUSTOM_PROMPT = "請問什麼時候提醒？例如：\n每天 17:00\n每週三 15:00\n2026-07-30 20:45"
_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")
_KIND_BY_CHOICE = {
    "1": ScheduleKind.MEDICATION,
    "2": ScheduleKind.APPOINTMENT,
    "3": ScheduleKind.CUSTOM,
}
_SLOT_ORDER = ("morning", "noon", "evening", "bedtime")
_WEEKDAYS = "一二三四五六日"


class ScheduleMenu:
    def __init__(
        self,
        schedules: ScheduleService,
        accounts,
        sessions: BindingSessionStore,
        *,
        clock: Callable[[], datetime],
        slot_hours: dict[str, int],
        appointment_hour: int,
    ) -> None:
        self._schedules = schedules
        self._accounts = accounts
        self._sessions = sessions
        self._clock = clock
        self._slot_hours = slot_hours
        self._appointment_hour = appointment_hour

    # ── 會話 ──

    def _save(self, line_user_id: str, state: BindingState, data: dict) -> None:
        self._sessions.save(BindingSession(line_user_id, state, data, self._clock().timestamp()))

    def open(self, line_user_id: str) -> str:
        self._save(line_user_id, BindingState.SCHED_MENU, {})
        return _MENU

    def step(self, session: BindingSession, text: str, line_user_id: str) -> str:
        state = session.state
        if state == BindingState.SCHED_MENU:
            return self._menu(text, line_user_id)
        if state == BindingState.SCHED_PICK_ELDER:
            return self._pick_elder(session, text, line_user_id)
        if state == BindingState.SCHED_ADD_KIND:
            return self._add_kind(session, text, line_user_id)
        if state == BindingState.SCHED_ADD_TITLE:
            return self._add_title(session, text, line_user_id)
        if state == BindingState.SCHED_ADD_WHEN:
            return self._add_when(session, text, line_user_id)
        return self._del_pick(session, text, line_user_id)

    # ── 選單 ──

    def _menu(self, text: str, line_user_id: str) -> str:
        action = {"1": "add", "2": "view", "3": "del"}.get(text.translate(_FULLWIDTH))
        if action is None:
            return "請回覆 1、2 或 3。"
        elders = self._accounts.elders_managed_by(line_user_id)
        if not elders:
            return "您還沒有長輩檔案，請先回覆「設定」並選 1 建立。"
        if len(elders) == 1:
            return self._begin(action, elders[0].elder_id, elders[0].name, line_user_id)
        self._save(
            line_user_id,
            BindingState.SCHED_PICK_ELDER,
            {"action": action, "elders": [[e.elder_id, e.name] for e in elders]},
        )
        listing = "\n".join(f"{i + 1}. {e.name}" for i, e in enumerate(elders))
        return "請回覆數字選擇長輩：\n" + listing

    def _pick_elder(self, session: BindingSession, text: str, line_user_id: str) -> str:
        elders = session.data["elders"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(elders)):
            return "請回覆清單中的數字。"
        elder_id, elder_name = elders[int(choice) - 1]
        return self._begin(session.data["action"], elder_id, elder_name, line_user_id)

    def _begin(self, action: str, elder_id: str, elder_name: str, line_user_id: str) -> str:
        if action == "add":
            self._save(
                line_user_id,
                BindingState.SCHED_ADD_KIND,
                {"elder_id": elder_id, "elder_name": elder_name},
            )
            return f"要幫『{elder_name}』新增提醒。\n{_KIND_PROMPT}"
        groups = self._schedules.groups_for_elder(elder_id)
        if action == "view":
            self._sessions.delete(line_user_id)
            if not groups:
                return f"『{elder_name}』目前沒有任何提醒。"
            lines = "\n".join(f"• {self._describe(g)}" for g in groups)
            return f"『{elder_name}』的提醒：\n" + lines
        if not groups:
            self._sessions.delete(line_user_id)
            return f"『{elder_name}』目前沒有任何提醒。"
        items = [[g.group_id, self._describe(g)] for g in groups]
        self._save(line_user_id, BindingState.SCHED_DEL_PICK, {"groups": items})
        listing = "\n".join(f"{i + 1}. {label}" for i, (_, label) in enumerate(items))
        return "請回覆要刪除的編號：\n" + listing

    # ── 新增 ──

    def _add_kind(self, session: BindingSession, text: str, line_user_id: str) -> str:
        kind = _KIND_BY_CHOICE.get(text.translate(_FULLWIDTH))
        if kind is None:
            return "請回覆 1、2 或 3。"
        data = {**session.data, "kind": kind.value}
        self._save(line_user_id, BindingState.SCHED_ADD_TITLE, data)
        asking = {
            ScheduleKind.MEDICATION: "請問要新增什麼藥？（回覆藥名）",
            ScheduleKind.APPOINTMENT: "請問是什麼回診？（例：心臟科回診 林口長庚）",
            ScheduleKind.CUSTOM: "請問要提醒什麼事？（例：去公園散步）",
        }
        return asking[kind]

    def _add_title(self, session: BindingSession, text: str, line_user_id: str) -> str:
        title = text.strip()
        if not title:
            return "請回覆要提醒的事情。"
        data = {**session.data, "title": title}
        self._save(line_user_id, BindingState.SCHED_ADD_WHEN, data)
        return self._when_prompt(ScheduleKind(data["kind"]))

    def _add_when(self, session: BindingSession, text: str, line_user_id: str) -> str:
        data = session.data
        kind = ScheduleKind(data["kind"])
        try:
            occurrences, event_at, notice = self._parse_when(kind, text)
        except TimeParseError as exc:
            return f"{exc}\n{self._when_prompt(kind)}"
        try:
            self._schedules.create(
                elder_id=data["elder_id"],
                kind=kind,
                title=data["title"],
                created_by=CreatedBy.GUARDIAN,
                occurrences=occurrences,
                event_at=event_at,
            )
        except ScheduleValidationError as exc:
            return f"{exc}\n{self._when_prompt(kind)}"
        self._sessions.delete(line_user_id)
        groups = self._schedules.groups_for_elder(data["elder_id"])
        added = next((g for g in groups if g.title == data["title"]), None)
        detail = self._describe(added) if added else data["title"]
        confirmation = f"已為『{data['elder_name']}』新增：{detail}。"
        # 少建一顆鬧鐘不可以靜默——清單只顯示「一件事」，家屬沒有別的地方會發現。
        return f"{confirmation}\n{notice}" if notice else confirmation

    def _del_pick(self, session: BindingSession, text: str, line_user_id: str) -> str:
        groups = session.data["groups"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(groups)):
            return "請回覆清單中的編號。"
        group_id, label = groups[int(choice) - 1]
        # 家屬可以刪長輩自己設的（反向才禁止），故 requested_by 固定為 GUARDIAN。
        self._schedules.cancel_group(group_id, requested_by=CreatedBy.GUARDIAN)
        self._sessions.delete(line_user_id)
        return f"已刪除『{label}』。"

    # ── 三種類型的差異全部收在這一對函式 ──

    def _when_prompt(self, kind: ScheduleKind) -> str:
        if kind == ScheduleKind.MEDICATION:
            return _SLOT_PROMPT
        if kind == ScheduleKind.APPOINTMENT:
            return _APPT_PROMPT
        return _CUSTOM_PROMPT

    def _parse_when(
        self, kind: ScheduleKind, text: str
    ) -> tuple[tuple[Occurrence, ...], float | None, str]:
        """回傳（鬧鐘, 事件時刻, 要補告訴家屬的話——沒有就空字串）。

        第三格只有回診用得到（前一天那顆已經過期而沒建），但由這裡統一回傳，
        呼叫端才不必知道哪一種類型會說話。
        """
        cleaned = text.strip()
        if kind == ScheduleKind.MEDICATION:
            return self._parse_medication_when(cleaned), None, ""
        if kind == ScheduleKind.APPOINTMENT:
            return self._parse_appointment_when(cleaned)
        return (self._parse_custom_when(cleaned),), None, ""

    def _parse_medication_when(self, text: str) -> tuple[Occurrence, ...]:
        """數字＝早中晚睡四時段（沿用家屬熟悉的問法），也接受直接輸入時刻。"""
        if ":" in text:
            hhmm = text.translate(_FULLWIDTH)
            return (self._daily_at(hhmm),)
        digits = [c for c in text.translate(_FULLWIDTH) if c in "1234"]
        if not digits:
            raise TimeParseError("請回覆 1～4 的數字（可複選），或直接輸入時刻如 07:30。")
        chosen = sorted({int(d) - 1 for d in digits})
        return tuple(
            Occurrence(RepeatKind.DAILY, repeat_time=f"{self._slot_hours[_SLOT_ORDER[i]]:02d}:00")
            for i in chosen
        )

    def _parse_appointment_when(self, text: str) -> tuple[tuple[Occurrence, ...], float, str]:
        """回診固定兩個鬧鐘（前一天＋當天）。

        推算改共用 `timeparse.build_appointment_reminders`——那份現在也是 REST 入口的
        唯一答案（12 §9 F-16 的修法）。連帶得到「已過期的那顆略過」：原本下午替明天
        的回診設提醒，會因為「前一天 08:00」＝今天早上而整筆建不起來。
        """
        parts = text.replace("　", " ").split()
        date_text = parts[0] if parts else ""
        time_text = parts[1] if len(parts) > 1 else ""
        now = self._clock()
        event_at = parse_epoch(date_text, time_text, now=now)
        reminders = build_appointment_reminders(
            event_at=event_at, hour=self._appointment_hour, now=now
        )
        notice = (
            appointment_day_before_skipped_text(self._appointment_hour)
            if reminders.is_day_before_skipped
            else ""
        )
        return reminders.occurrences, event_at, notice

    def _parse_custom_when(self, text: str) -> Occurrence:
        parts = text.replace("　", " ").split()
        if len(parts) != 2:
            raise TimeParseError("請照範例格式回覆。")
        head, hhmm = parts[0], parts[1].translate(_FULLWIDTH)
        if head == "每天":
            return self._daily_at(hhmm)
        if head.startswith("每週") and len(head) == 3:
            index = _WEEKDAYS.find(head[2])
            if index < 0:
                raise TimeParseError("星期只能是一到日。")
            occurrence = self._daily_at(hhmm)
            return Occurrence(
                RepeatKind.WEEKLY,
                repeat_time=occurrence.repeat_time,
                repeat_weekday=index,
            )
        return Occurrence(RepeatKind.ONCE, scheduled_at=parse_epoch(head, hhmm, now=self._clock()))

    def _daily_at(self, hhmm: str) -> Occurrence:
        from kinsun.schedules.timeparse import build_occurrence

        return build_occurrence(repeat="daily", time_text=hhmm, now=self._clock())

    # ── 顯示 ──

    def _describe(self, group) -> str:
        first = group.schedules[0]
        if group.kind == ScheduleKind.MEDICATION:
            labels = "、".join(
                slot_label(int(s.repeat_time[:2])) for s in group.schedules if s.repeat_time
            )
            return f"{group.title}（{labels}）"
        now = self._clock()
        if group.kind == ScheduleKind.APPOINTMENT and group.event_at is not None:
            event = datetime.fromtimestamp(group.event_at, now.tzinfo)
            stamp = event.strftime("%Y-%m-%d")
            if event.hour or event.minute:
                stamp += event.strftime(" %H:%M")
            return f"{group.title}（{stamp}）"
        if first.repeat_kind == RepeatKind.DAILY:
            return f"{group.title}（每天 {first.repeat_time}）"
        if first.repeat_kind == RepeatKind.WEEKLY:
            weekday = _WEEKDAYS[first.repeat_weekday] if first.repeat_weekday is not None else ""
            return f"{group.title}（每週{weekday} {first.repeat_time}）"
        when = datetime.fromtimestamp(first.scheduled_at, now.tzinfo) if first.scheduled_at else now
        return f"{group.title}（{when.strftime('%Y-%m-%d %H:%M')}）"
