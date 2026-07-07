"""用藥事實提供者：把長輩當前用藥組成注入情境的一段（FactSection）。"""

from __future__ import annotations

from kinsun.medications.models import slots_label
from kinsun.memory.models import FactSection

_TITLE = "\n這位長者目前固定服用的藥（系統設定的提醒時段，僅供參考、非醫療指示）：\n"


class MedicationFacts:
    """facts(elder_id) -> FactSection | None（無用藥回 None）。"""

    def __init__(self, medications) -> None:
        self._medications = medications

    def facts(self, elder_id: str) -> FactSection | None:
        meds = self._medications.list_for_elder(elder_id)
        if not meds:
            return None
        return FactSection(_TITLE, [f"{m.name}（{slots_label(m.slots)}）" for m in meds])
