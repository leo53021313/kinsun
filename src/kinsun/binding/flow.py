"""綁定引導式對話狀態機。handle 永不上拋；非綁定文字回 None。"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun.accounts.models import ConsentBy, InviteRole
from kinsun.accounts.service import AccountService, InviteError, InvitePreview
from kinsun.binding.session import BindingSession, BindingSessionStore, BindingState

logger = logging.getLogger("kinsun.binding")


class Profiles(Protocol):
    def display_name(self, user_id: str) -> str: ...


_TRIGGERS = {"設定", "綁定", "選單"}
_GLOBAL_CANCEL = {"取消", "結束"}
_YES = {"是", "好", "確認"}
_NO = {"否", "不要", "取消"}
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{16,}$")
_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")

_MENU = (
    "您好，我是金孫。請回覆數字：\n"
    "1️⃣ 建立長輩檔案\n"
    "2️⃣ 邀請其他家屬\n"
    "3️⃣ 綁定（貼上邀請碼）\n"
    "4️⃣ 用藥提醒\n"
    "5️⃣ 回診提醒\n"
    "（隨時回覆「取消」可結束）"
)
_REASON_MSG = {
    "not_found": "找不到這組邀請碼，請確認後再貼一次。",
    "used": "這組邀請碼已經被使用過了。",
    "expired": "這組邀請碼已過期，請家屬重新產生一組。",
    "too_many_attempts": "這組邀請碼嘗試次數過多，請家屬重新產生一組。",
}


class BindingFlow:
    def __init__(
        self,
        accounts: AccountService,
        sessions: BindingSessionStore,
        profiles: Profiles,
        medication,
        appointment,
        *,
        clock: Callable[[], datetime],
        session_ttl_seconds: int = 600,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._profiles = profiles
        self._medication = medication
        self._appointment = appointment
        self._clock = clock
        self._ttl = session_ttl_seconds

    def handle(self, line_user_id: str, text: str) -> str | None:
        try:
            return self._handle(line_user_id, text.strip())
        except Exception:  # noqa: BLE001
            logger.exception("綁定流程異常 line=%s", line_user_id)
            self._sessions.delete(line_user_id)
            return "系統忙線，請稍後再試一次。"

    def _now(self) -> float:
        return self._clock().timestamp()

    def _save(self, line: str, state: BindingState, data: dict) -> None:
        self._sessions.save(BindingSession(line, state, data, self._now()))

    def _handle(self, line: str, text: str) -> str | None:
        session = self._sessions.get(line)
        if session is not None and self._now() - session.updated_at > self._ttl:
            self._sessions.delete(line)
            session = None
        if session is not None:
            if session.state != BindingState.AWAIT_CONFIRM and text in _GLOBAL_CANCEL:
                self._sessions.delete(line)
                return "已取消。"
            return self._step(session, text, line)
        if text in _TRIGGERS:
            self._save(line, BindingState.MENU, {})
            return _MENU
        if _CODE_RE.match(text):
            preview = self._accounts.preview_invite(text)
            if preview is not None:
                if preview.reason is not None:
                    return _REASON_MSG[preview.reason]
                return self._enter_confirm(line, text, preview)
        return None

    def _step(self, session: BindingSession, text: str, line: str) -> str:
        state = session.state
        if state.value.startswith("med_"):
            return self._medication.step(session, text, line)
        if state.value.startswith("appt_"):
            return self._appointment.step(session, text, line)
        if state == BindingState.MENU:
            return self._menu(text, line)
        if state == BindingState.AWAIT_ELDER_NAME:
            return self._create_elder(line, text)
        if state == BindingState.AWAIT_ELDER_PICK:
            return self._pick_elder(session, text, line)
        if state == BindingState.AWAIT_CODE:
            return self._submit_code(text, line)
        return self._confirm(session, text, line)

    def _menu(self, text: str, line: str) -> str:
        choice = text.translate(_FULLWIDTH)
        if choice == "1":
            self._save(line, BindingState.AWAIT_ELDER_NAME, {})
            return "請問長輩怎麼稱呼？（例：阿公、王媽媽）"
        if choice == "2":
            elders = self._accounts.elders_managed_by(line)
            if not elders:
                return "您還沒有長輩檔案，請先回覆「設定」並選 1 建立。"
            if len(elders) == 1:
                return self._guardian_invite(line, elders[0].elder_id, elders[0].name)
            self._save(
                line,
                BindingState.AWAIT_ELDER_PICK,
                {"elders": [[e.elder_id, e.name] for e in elders]},
            )
            listing = "\n".join(f"{i + 1}. {e.name}" for i, e in enumerate(elders))
            return "請回覆數字選擇要邀請家屬的長輩：\n" + listing
        if choice == "3":
            self._save(line, BindingState.AWAIT_CODE, {})
            return "請貼上您收到的邀請碼。"
        if choice == "4":
            return self._medication.open(line)
        if choice == "5":
            return self._appointment.open(line)
        return "請回覆 1、2、3、4 或 5。"

    def _create_elder(self, line: str, name: str) -> str:
        display = self._profiles.display_name(line)
        elder = self._accounts.create_elder(line, display, name)
        invite = self._accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
        self._sessions.delete(line)
        return (
            f"已建立『{elder.name}』的檔案，您是主要家屬。"
            f"請把這組綁定碼交給『{elder.name}』，在金孫聊天視窗貼上：\n"
            f"{invite.code}\n（24 小時內有效）"
        )

    def _pick_elder(self, session: BindingSession, text: str, line: str) -> str:
        elders = session.data["elders"]
        choice = text.translate(_FULLWIDTH)
        if not choice.isdigit() or not (1 <= int(choice) <= len(elders)):
            return "請回覆清單中的數字。"
        elder_id, elder_name = elders[int(choice) - 1]
        return self._guardian_invite(line, elder_id, elder_name)

    def _guardian_invite(self, line: str, elder_id: str, elder_name: str) -> str:
        invite = self._accounts.generate_invite(elder_id, InviteRole.GUARDIAN)
        self._sessions.delete(line)
        return (
            f"這是『{elder_name}』的家人邀請碼，請交給其他家屬，在金孫聊天視窗貼上：\n"
            f"{invite.code}\n（24 小時內有效）"
        )

    def _submit_code(self, code: str, line: str) -> str:
        preview = self._accounts.preview_invite(code)
        if preview is None:
            return _REASON_MSG["not_found"]
        if preview.reason is not None:
            self._sessions.delete(line)
            return _REASON_MSG[preview.reason]
        return self._enter_confirm(line, code, preview)

    def _enter_confirm(self, line: str, code: str, preview: InvitePreview) -> str:
        self._save(line, BindingState.AWAIT_CONFIRM, {"code": code, "role": preview.role.value})
        if preview.role == InviteRole.ELDER:
            return (
                f"您要綁定為『{preview.elder_name}』本人嗎？綁定後金孫會記錄您的對話，"
                "以提供關懷並在必要時通知家人。同意請回覆『是』，取消請回覆『否』。"
            )
        return f"您要成為『{preview.elder_name}』的家人嗎？同意請回覆『是』，取消請回覆『否』。"

    def _confirm(self, session: BindingSession, text: str, line: str) -> str:
        if text in _YES:
            code = session.data["code"]
            try:
                self._accounts.redeem_invite(code, line, consent_by=ConsentBy.SELF)
            except InviteError as exc:
                self._sessions.delete(line)
                return _REASON_MSG.get(exc.reason, "綁定失敗，請重新操作。")
            self._sessions.delete(line)
            if session.data.get("role") == InviteRole.ELDER.value:
                return "綁定成功！您可以開始用語音跟金孫聊天囉。"
            return "綁定成功！長輩有狀況時，金孫會通知您。"
        if text in _NO:
            self._sessions.delete(line)
            return "已取消綁定。"
        return "請回覆『是』或『否』。"
