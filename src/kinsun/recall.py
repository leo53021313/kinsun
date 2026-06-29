"""記憶情境聚合器：長期記憶 ＋ 各事實提供者 → system prompt 注入字串。"""

from __future__ import annotations

from typing import Protocol

from kinsun.longterm.store import LongTermStore


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
            out += provider.facts(session_id)
        return out
