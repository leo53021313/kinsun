"""記憶情境聚合器：把長期記憶檢索結果組成 system prompt 注入字串。"""

from __future__ import annotations

from kinsun.longterm.store import LongTermStore


class MemoryContext:
    def __init__(self, long_term: LongTermStore) -> None:
        self._long_term = long_term

    def recall(self, session_id: str, user_text: str) -> str:
        return self._long_term.search(session_id, user_text)
