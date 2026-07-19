"""會話記憶門面：短期記憶讀寫 ＋ 長期記憶 ＋ 事實 → 單輪情境（TurnContext）。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.longterm.store import LongTermStore
from kinsun.memory.models import FactSection, InjectedContext, TurnContext
from kinsun.memory.shortterm import MemoryStore

logger = logging.getLogger("kinsun.memory.recall")


class FactProvider(Protocol):
    def facts(self, elder_id: str) -> FactSection | None: ...


class SessionMemory:
    """CareAgent 對「本次會話短期記憶 ＋ 情境」的單一門面。

    assemble 一手包三層（今日對話 ＋ 長期記憶 ＋ 事實）→ TurnContext；
    record_turn 記錄本輪。agent 不再直接碰 MemoryStore。
    """

    def __init__(
        self,
        short_term: MemoryStore,
        long_term: LongTermStore,
        *,
        facts: list[FactProvider] | None = None,
    ) -> None:
        self._short_term = short_term
        self._long_term = long_term
        self._facts = facts or []

    @tracing.track(name="memory_assemble", type="general", capture_input=False, capture_output=False)
    def assemble(self, elder_id: str, query: str) -> TurnContext:
        return TurnContext(
            injected=self._inject(elder_id, query),
            history=self._short_term.recent(elder_id),
        )

    def record_turn(self, elder_id: str, *messages: Message) -> None:
        for message in messages:
            self._short_term.append(elder_id, message)

    def _inject(self, elder_id: str, query: str) -> InjectedContext:
        memories = self._long_term.search(elder_id, query)
        sections = []
        for provider in self._facts:
            try:
                section = provider.facts(elder_id)
            except Exception:  # noqa: BLE001 - 事實提供者失敗不可中斷對話
                logger.warning("事實提供者失敗，略過該段")
                continue
            if section is not None:
                sections.append(section)
        return InjectedContext(memories=memories, sections=sections)
