"""用藥事實提供者：把長輩當前用藥組成注入情境的一段文字。"""

from __future__ import annotations

from kinsun.medication.models import slots_label

_PREFIX = "\n這位長者目前固定服用的藥（系統設定的提醒時段，僅供參考、非醫療指示）：\n"


class MedicationFacts:
    """facts(session_id) -> 注入文字。session_id 即長輩的 LINE user_id。"""

    def __init__(self, accounts, medications) -> None:
        self._accounts = accounts
        self._medications = medications

    def facts(self, session_id: str) -> str:
        elder = self._accounts.elder_by_line(session_id)
        if elder is None:
            return ""
        meds = self._medications.list_for_elder(elder.elder_id)
        if not meds:
            return ""
        lines = "\n".join(f"- {m.name}（{slots_label(m.slots)}）" for m in meds)
        return _PREFIX + lines + "\n"
