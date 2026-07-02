"""記憶情境聚合器：長期記憶 ＋ 各事實提供者 → system prompt 注入字串。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.memory.longterm.store import LongTermStore

logger = logging.getLogger("kinsun.memory.recall")


class FactProvider(Protocol):
    def facts(self, session_id: str) -> str: ...


class MemoryContext:
    def __init__(
        self, long_term: LongTermStore, *, facts: list[FactProvider] | None = None
    ) -> None:
        self._long_term = long_term
        self._facts = facts or []

    def recall(self, session_id: str, query: str) -> str:
        out = self._long_term.search(session_id, query)
        for provider in self._facts:
            try:
                out += provider.facts(session_id)
            except Exception:  # noqa: BLE001 - 事實提供者失敗不可中斷對話
                logger.warning("事實提供者失敗，略過該段")
        return out
