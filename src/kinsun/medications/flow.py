"""用藥提醒的引導式設定（被引導流程委派，共用 session）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.binding.session import BindingSession, BindingSessionStore, BindingState
from kinsun.medications.models import SLOT_ORDER, MedicationSlot, slots_label
from kinsun.medications.service import MedicationService

_MED_MENU = "用藥提醒：請回覆數字：\n1️⃣ 新增用藥\n2️⃣ 查看用藥\n3️⃣ 刪除用藥"
_SLOT_PROMPT = (
    "請問什麼時候吃？回覆數字（可複選）：\n"
    "1 早上　2 中午　3 晚上　4 睡前\n（例如「1 3」表示早上和晚上）"
)
_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")


def _parse_slots(text: str) -> tuple[MedicationSlot, ...] | None:
    digits = [c for c in text.translate(_FULLWIDTH) if c in "1234"]
    if not digits:
        return None
    chosen = {SLOT_ORDER[int(d) - 1] for d in digits}
    return tuple(s for s in SLOT_ORDER if s in chosen)


class MedicationMenu:
    def __init__(
        self,
        medications: MedicationService,
        accounts,
        sessions: BindingSessionStore,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._meds = medications
        self._accounts = accounts
        self._sessions = sessions
        self._clock = clock

    def _save(self, line: str, state: BindingState, data: dict) -> None:
        self._sessions.save(BindingSession(line, state, data, self._clock().timestamp()))

    def open(self, line: str) -> str:
        self._save(line, BindingState.MED_MENU, {})
        return _MED_MENU

    def step(self, session: BindingSession, text: str, line: str) -> str:
        state = session.state
        if state == BindingState.MED_MENU:
            return self._menu(text, line)
        if state == BindingState.MED_PICK_ELDER:
            return self._pick_elder(session, text, line)
        if state == BindingState.MED_ADD_NAME:
            return self._add_name(session, text, line)
        if state == BindingState.MED_ADD_SLOTS:
            return self._add_slots(session, text, line)
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
            BindingState.MED_PICK_ELDER,
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
                line, BindingState.MED_ADD_NAME, {"elder_id": elder_id, "elder_name": elder_name}
            )
            return f"請問要幫『{elder_name}』新增什麼藥？（回覆藥名）"
        if action == "view":
            self._sessions.delete(line)
            return self._view(elder_id, elder_name)
        meds = self._meds.list_for_elder(elder_id)
        if not meds:
            self._sessions.delete(line)
            return f"『{elder_name}』目前沒有設定用藥。"
        items = [[m.med_id, f"{m.name}（{slots_label(m.slots)}）"] for m in meds]
        self._save(line, BindingState.MED_DEL_PICK, {"meds": items})
        listing = "\n".join(f"{i + 1}. {label}" for i, (_, label) in enumerate(items))
        return "請回覆要刪除的編號：\n" + listing

    def _view(self, elder_id: str, elder_name: str) -> str:
        meds = self._meds.list_for_elder(elder_id)
        if not meds:
            return f"『{elder_name}』目前沒有設定用藥。"
        lines = "\n".join(f"• {m.name}（{slots_label(m.slots)}）" for m in meds)
        return f"『{elder_name}』的用藥：\n" + lines

    def _add_name(self, session: BindingSession, text: str, line: str) -> str:
        data = dict(session.data)
        data["name"] = text
        self._save(line, BindingState.MED_ADD_SLOTS, data)
        return _SLOT_PROMPT

    def _add_slots(self, session: BindingSession, text: str, line: str) -> str:
        slots = _parse_slots(text)
        if slots is None:
            return "請回覆 1～4 的數字（可複選），例如「1 3」。"
        data = session.data
        self._meds.add(data["elder_id"], data["name"], slots)
        self._sessions.delete(line)
        return f"已為『{data['elder_name']}』新增『{data['name']}』（{slots_label(slots)}）。"

    def _del_pick(self, session: BindingSession, text: str, line: str) -> str:
        meds = session.data["meds"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(meds)):
            return "請回覆清單中的編號。"
        med_id, label = meds[int(choice) - 1]
        self._meds.remove(med_id)
        self._sessions.delete(line)
        return f"已刪除『{label}』。"
