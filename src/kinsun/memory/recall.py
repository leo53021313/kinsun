"""會話記憶門面：短期記憶讀寫 ＋ 長期記憶 ＋ 事實 → 單輪情境（TurnContext）。"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.longterm.store import LongTermStore
from kinsun.memory.models import FactSection, InjectedContext, TurnContext
from kinsun.memory.shortterm import MemoryStore
from kinsun.turn_context import current_pending_utterances

logger = logging.getLogger("kinsun.memory.recall")

# 單一事實提供者的等待上限（秒）。
#
# 5 秒是「正常查詢的十倍餘裕、又明顯低於情境組裝的 15 秒總上限」：單次 Supabase
# 往返實測約 0.21 秒，慢到 5 秒代表它正卡在連線池上或那張表被鎖住，此時「這一段
# 缺席」遠好過「拖著整輪一起撞 15 秒逾時、長輩拿到回退話術」。
_FACT_TIMEOUT_SECONDS = 5.0


class FactProvider(Protocol):
    def facts(self, elder_id: str) -> FactSection | None: ...


def _section_or_none(future) -> FactSection | None:
    """取一路事實的結果；等太久就視同該段缺席（見 `_gather_facts` 的 ⚠️ 說明）。"""
    try:
        return future.result(timeout=_FACT_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        logger.warning("事實提供者逾時（%.1f 秒），略過該段", _FACT_TIMEOUT_SECONDS)
        return None


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
        """今日對話／長期記憶／七路事實三段並行（2026-07-30 延遲優化 A2）。

        三段彼此無依賴：`recent` 只吃 `elder_id`、`long_term.search` 吃
        `elder_id`＋`query`、`gather_facts` 只吃 `elder_id`；串行跑等於白等
        最慢那段以外的全部時間（實測 mem0 檢索本身就是最慢路，並行後總耗時
        ≈ 它一段，而不是三段相加）。

        `contextvars.copy_context()` 帶入呼叫端 context，三顆 Opik span 與
        `gather_facts` 內部既有的七路並行才不會巢狀消失（與 `_gather_facts`
        自己的既有作法同一套）。

        ⚠️ **刻意不用 `with ThreadPoolExecutor(...)`**（2026-07-30 審查 H3）：`with`
        的 `__exit__` 是 `shutdown(wait=True)`，於是任一段失敗時，例外要等**三段都
        跑完**才冒得出區塊（實測：`recent` 在 0.05 秒失敗、例外 2.00 秒才出現）。
        兩個後果：失敗路徑的延遲從「最快那段」變成「最慢那段」；更糟的是若最慢那段
        超過 `CONTEXT_ASSEMBLY_TIMEOUT_SECONDS`，`PreparedTurn.context()` 的
        `join` 會先到期、把真正的根因（例如短期記憶讀取失敗）改寫成「情境組裝逾時」
        ——留一個看起來很有把握的錯誤根因，下一個人會往錯的方向找。
        """
        contexts = [contextvars.copy_context() for _ in range(3)]
        pool = ThreadPoolExecutor(max_workers=3)
        try:
            recent_future = pool.submit(contexts[0].run, self._short_term.recent, elder_id)
            memories_future = pool.submit(contexts[1].run, self._long_term.search, elder_id, query)
            facts_future = pool.submit(contexts[2].run, self._gather_facts, elder_id)
            history = recent_future.result()
            memories = memories_future.result()
            sections = facts_future.result()
        finally:
            # wait=False：這一輪要嘛已經成功、要嘛正在往回退話術走，都不必替它等完
            # 最慢那段。殘餘的孤兒執行緒與 `PreparedTurn.context()` 逾時放棄時的
            # 既有殘餘風險同性質（見 agent.py 該處說明）。
            pool.shutdown(wait=False, cancel_futures=True)
        # 併發輪的在途問句（spec 2026-07-28 P3）：長輩問完新聞、接著問「那天氣呢」時，
        # 新聞那一輪還沒寫進 turns 表（記憶只在回覆產生後才寫），少了它「那」就沒有
        # 指涉對象。補在歷史尾巴＝時序上正好在這一輪的問句之前。
        # 沒有人提供在途清單時（LINE、POST /turns、排程端）整段為空，行為不變。
        history = [*history, *(Message("user", text) for text in current_pending_utterances())]
        return TurnContext(
            injected=InjectedContext(memories=memories, sections=sections),
            history=history,
        )

    def record_turn(self, elder_id: str, *messages: Message, at: datetime | None = None) -> None:
        """`at`＝長輩開口的時刻，供併發輪維持正確的對話順序（見 `shortterm.append`）。"""
        for message in messages:
            self._short_term.append(elder_id, message, at=at)

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

        併發度＝提供者數量（目前 7 個，其中 6 個碰 DB——`TimeFacts` 純算時間），刻意
        不另設上限：真正的節流閥是 psycopg 連線池（`DATABASE_POOL_MAX_SIZE`，**正式
        環境為 3**），多出來的查詢自然在池上排隊。⚠️ A2（`assemble` 三段並行）之後
        `recent` 會與這 6 條同時搶那 3 條連線，峰值需求 6→7；淨值仍是賺（總耗時從
        三段相加收斂到最慢那段），但「自然排隊」的餘裕已經很薄。

        ⚠️ 每段各有 `_FACT_TIMEOUT_SECONDS` 上限（2026-07-30 審查 H4）：沒有它，
        `PreparedTurn.context()` 逾時放棄後這些執行緒仍握著 psycopg 連線不放，而
        逾時率實測 10%——孤兒會繼續搶那 3 條連線、讓活著的輪更容易逾時，形成正回饋。
        逾時視同「該段缺席」（`fetch` 本來就允許回 None），不是錯誤。
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
        pool = ThreadPoolExecutor(max_workers=len(providers))
        try:
            futures = [
                pool.submit(context.run, fetch, provider_facts)
                for context, provider_facts in zip(contexts, providers, strict=True)
            ]
            sections = [_section_or_none(future) for future in futures]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return [section for section in sections if section is not None]
