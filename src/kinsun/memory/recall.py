"""會話記憶門面：短期記憶讀寫 ＋ 長期記憶 ＋ 事實 → 單輪情境（TurnContext）。"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.longterm.store import LongTermStore
from kinsun.memory.models import FactSection, InjectedContext, TurnContext
from kinsun.memory.shortterm import MemoryStore
from kinsun.turn_context import current_pending_utterances

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
        # 逐提供者包 span（2026-07-30 spec）：索引＝注入順序——ScheduleFacts 註冊
        # 三次（三種 kind），純類名會撞名；且順序本身是 prompt 契約，帶序號的
        # waterfall 直接對得上段落順序。一次性包在建構時，wrapper 內的 lazy opik
        # 快取才能跨輪重用。output 開是 capture 總原則的唯一例外：合併結果看不到
        # 「哪一路回了 None（該段缺席）」，而缺席正是排查時要看的東西。
        self._tracked_facts = [
            tracing.track(
                name=f"facts_{index}_{type(provider).__name__}",
                capture_input=True,
                capture_output=True,
            )(provider.facts)
            for index, provider in enumerate(self._facts)
        ]

    # capture_output=True：回傳的 TurnContext（注入情境＋歷史）是乾淨資料、不含 self，
    # 攤在 span 上可直接看到模型當輪被餵了什麼記憶與事實。input 仍關（首參是 self）。
    @tracing.track(name="memory_assemble", type="general", capture_input=True, capture_output=True)
    def assemble(self, elder_id: str, query: str) -> TurnContext:
        history = self._short_term.recent(elder_id)
        # 併發輪的在途問句（spec 2026-07-28 P3）：長輩問完新聞、接著問「那天氣呢」時，
        # 新聞那一輪還沒寫進 turns 表（記憶只在回覆產生後才寫），少了它「那」就沒有
        # 指涉對象。補在歷史尾巴＝時序上正好在這一輪的問句之前。
        # 沒有人提供在途清單時（LINE、POST /turns、排程端）整段為空，行為不變。
        history = [*history, *(Message("user", text) for text in current_pending_utterances())]
        return TurnContext(
            injected=self._inject(elder_id, query),
            history=history,
        )

    def record_turn(self, elder_id: str, *messages: Message, at: datetime | None = None) -> None:
        """`at`＝長輩開口的時刻，供併發輪維持正確的對話順序（見 `shortterm.append`）。"""
        for message in messages:
            self._short_term.append(elder_id, message, at=at)

    def _inject(self, elder_id: str, query: str) -> InjectedContext:
        memories = self._long_term.search(elder_id, query)
        return InjectedContext(memories=memories, sections=self._gather_facts(elder_id))

    @tracing.track(name="gather_facts", capture_input=True, capture_output=False)
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
        providers = self._tracked_facts
        if not providers:
            return []

        def fetch(provider_facts) -> FactSection | None:
            try:
                return provider_facts(elder_id)
            except Exception:  # noqa: BLE001 - 事實提供者失敗不可中斷對話
                logger.warning("事實提供者失敗，略過該段")
                return None

        contexts = [contextvars.copy_context() for _ in providers]
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = [
                pool.submit(context.run, fetch, provider_facts)
                for context, provider_facts in zip(contexts, providers, strict=True)
            ]
            sections = [future.result() for future in futures]
        return [section for section in sections if section is not None]
