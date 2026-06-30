"""回診提醒的引導式設定（被引導流程委派，共用 session）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.appointment.service import AppointmentService
from kinsun.binding.session import BindingSession, BindingSessionStore, BindingState

_APPT_MENU = "回診提醒：請回覆數字：\n1️⃣ 新增回診\n2️⃣ 查看回診\n3️⃣ 刪除回診"
_DATE_PROMPT = "請問回診日期？請用 2026-07-15 這種格式（年-月-日）。"
_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")


def _parse_date(text: str) -> str | None:
    try:
        parsed = datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed.isoformat()


class AppointmentMenu:
    def __init__(
        self,
        appointments: AppointmentService,
        accounts,
        sessions: BindingSessionStore,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._appts = appointments
        self._accounts = accounts
        self._sessions = sessions
        self._clock = clock

    def _save(self, line: str, state: BindingState, data: dict) -> None:
        self._sessions.save(BindingSession(line, state, data, self._clock().timestamp()))

    def open(self, line: str) -> str:
        self._save(line, BindingState.APPT_MENU, {})
        return _APPT_MENU

    def step(self, session: BindingSession, text: str, line: str) -> str:
        state = session.state
        if state == BindingState.APPT_MENU:
            return self._menu(text, line)
        if state == BindingState.APPT_PICK_ELDER:
            return self._pick_elder(session, text, line)
        if state == BindingState.APPT_ADD_LABEL:
            return self._add_label(session, text, line)
        if state == BindingState.APPT_ADD_DATE:
            return self._add_date(session, text, line)
        return self._del_pick(session, text, line)

    def _menu(self, text: str, line: str) -> str:
        action = {"1": "add", "2": "view", "3": "del"}.get(text.translate(_FULLWIDTH))
        if action is None:
            return "請回覆 1、2 或 3。"
        elders = self._accounts.elders_managed_by(line)
        if not elders:
            return "您還沒有長輩檔案，請先回覆「設定」並選 1 建立。"
        if len(elders) == 1:
            return self._begin(action, elders[0].elder_id, elders[0].name, line)
        self._save(
            line,
            BindingState.APPT_PICK_ELDER,
            {"action": action, "elders": [[e.elder_id, e.name] for e in elders]},
        )
        listing = "\n".join(f"{i + 1}. {e.name}" for i, e in enumerate(elders))
        return "請回覆數字選擇長輩：\n" + listing

    def _pick_elder(self, session: BindingSession, text: str, line: str) -> str:
        elders = session.data["elders"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(elders)):
            return "請回覆清單中的數字。"
        elder_id, elder_name = elders[int(choice) - 1]
        return self._begin(session.data["action"], elder_id, elder_name, line)

    def _begin(self, action: str, elder_id: str, elder_name: str, line: str) -> str:
        if action == "add":
            self._save(
                line, BindingState.APPT_ADD_LABEL, {"elder_id": elder_id, "elder_name": elder_name}
            )
            return f"請問要幫『{elder_name}』記哪一個回診？（例：上午10點 心臟科回診 林口長庚）"
        if action == "view":
            self._sessions.delete(line)
            return self._view(elder_id, elder_name)
        appts = self._appts.list_for_elder(elder_id)
        if not appts:
            self._sessions.delete(line)
            return f"『{elder_name}』目前沒有設定回診。"
        items = [[a.appt_id, f"{a.date} {a.label}"] for a in appts]
        self._save(line, BindingState.APPT_DEL_PICK, {"appts": items})
        listing = "\n".join(f"{i + 1}. {label}" for i, (_, label) in enumerate(items))
        return "請回覆要刪除的編號：\n" + listing

    def _view(self, elder_id: str, elder_name: str) -> str:
        today = self._clock().date().isoformat()
        ups = self._appts.upcoming(elder_id, today)
        if not ups:
            return f"『{elder_name}』目前沒有即將到來的回診。"
        lines = "\n".join(f"• {a.date} {a.label}" for a in ups)
        return f"『{elder_name}』即將到來的回診：\n" + lines

    def _add_label(self, session: BindingSession, text: str, line: str) -> str:
        data = dict(session.data)
        data["label"] = text
        self._save(line, BindingState.APPT_ADD_DATE, data)
        return _DATE_PROMPT

    def _add_date(self, session: BindingSession, text: str, line: str) -> str:
        date = _parse_date(text)
        if date is None:
            return "請用 2026-07-15 這種格式（年-月-日）。"
        if date < self._clock().date().isoformat():
            return "這個日期已經過了，請輸入今天以後的日期。"
        data = session.data
        self._appts.add(data["elder_id"], date, data["label"])
        self._sessions.delete(line)
        return f"已為『{data['elder_name']}』新增回診：{date} {data['label']}。"

    def _del_pick(self, session: BindingSession, text: str, line: str) -> str:
        appts = session.data["appts"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(appts)):
            return "請回覆清單中的編號。"
        appt_id, label = appts[int(choice) - 1]
        self._appts.remove(appt_id)
        self._sessions.delete(line)
        return f"已刪除『{label}』。"
