"""長輩檔案事實提供者：把稱謂（或名字保底）注入情境。

為什麼需要這段：情境沒有任何稱呼資料時，模型每輪自行猜一個性別稱謂——
2026-07-17 全功能測試實測，同一位長輩一下被叫「阿公」一下被叫「阿嬤」，
真實使用有一半機率叫錯。稱謂由家屬設定（elders.nickname）；未設定時退回
名字並明令不得猜性別。
"""

from __future__ import annotations

from kinsun.memory.models import FactSection

_TITLE = "\n這位長者的稱呼（系統設定）：\n"


class ElderProfileFacts:
    """facts(elder_id) -> FactSection | None（查無長輩或無任何稱呼資料回 None）。"""

    def __init__(self, store) -> None:
        self._store = store

    def facts(self, elder_id: str) -> FactSection | None:
        elder = self._store.get_elder(elder_id)
        if elder is None:
            return None
        if elder.nickname:
            line = f"請用「{elder.nickname}」稱呼她／他，開頭問候也用這個稱呼。"
        elif elder.name:
            line = (
                f"她／他的名字是「{elder.name}」，可以自然地用名字稱呼。"
                "系統沒有性別資料，不要自行猜測用「阿公」或「阿嬤」這類稱謂，"
                "除非她／他自己說過。"
            )
        else:
            return None
        return FactSection(_TITLE, [line])
