"""會話記憶門面：短期記憶讀寫 ＋ 長期記憶 ＋ 事實 → 單輪情境（TurnContext）。"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
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

    # capture_output=True：回傳的 TurnContext（注入情境＋歷史）是乾淨資料、不含 self，
    # 攤在 span 上可直接看到模型當輪被餵了什麼記憶與事實。input 仍關（首參是 self）。
    @tracing.track(name="memory_assemble", type="general", capture_input=True, capture_output=True)
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
        return InjectedContext(memories=memories, sections=self._gather_facts(elder_id))

    def _gather_facts(self, elder_id: str) -> list[FactSection]:
        """並行查所有事實提供者，結果仍按注入順序排列。

        每個提供者都是一次獨立的 Supabase 查詢（稱呼／三種排程／守則／位置），實測
        單次跨網往返固定約 0.21 秒且彼此無依賴——排隊查等於白等約 1.5 秒
        （2026-07-26 延遲實測）。

        ⚠️ 順序是 prompt 契約、不是實作細節：段落先後由 composition.assemble_core
        的注入順序決定（時間必須排第一，它是其他事實的座標系；稱呼緊接其後）。
        故這裡按 `self._facts` 的索引回填，不可改用「誰先回來就先放」。

        以 `contextvars.copy_context()` 帶入呼叫端 context，Opik 的 span 巢狀與
        `turn_context.elder_utterance` 在子執行緒裡才不會憑空消失。

        併發度＝提供者數量（目前 7 個），刻意不另設上限：真正的節流閥是 psycopg
        連線池（`DATABASE_POOL_MAX_SIZE`，預設 5），多出來的查詢自然在池上排隊。
        """
        providers = self._facts
        if not providers:
            return []

        def fetch(provider: FactProvider) -> FactSection | None:
            try:
                return provider.facts(elder_id)
            except Exception:  # noqa: BLE001 - 事實提供者失敗不可中斷對話
                logger.warning("事實提供者失敗，略過該段")
                return None

        contexts = [contextvars.copy_context() for _ in providers]
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = [
                pool.submit(context.run, fetch, provider)
                for context, provider in zip(contexts, providers, strict=True)
            ]
            sections = [future.result() for future in futures]
        return [section for section in sections if section is not None]
