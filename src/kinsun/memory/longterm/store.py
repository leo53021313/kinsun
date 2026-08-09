"""長期記憶薄介面：把 Mem0 包在自有 Protocol 後，供 agent／consolidation 使用。"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.longterm import provenance as prov
from kinsun.memory.models import MemoryItem

logger = logging.getLogger(__name__)

# 每輪固定增補檢索：讓用藥/慢性病等穩定健康事實即使與當下話題無關也浮現。
#
# ⚠️ 不可改回**空格分隔**的關鍵字串（原為 "用藥 慢性病 過敏 回診 健康狀況"）：mem0 的
# `_search_vector_store` 會先跑 `extract_entities(query)`，抽得出實體就多跑一輪
# `_compute_entity_boosts`——一次 `embed_batch`（Gemini API）＋對 entity store 發
# `top_k=500` 的向量查詢。空格分隔會被判成實體，自然中文句不會。
# 2026-08-07 實測（真實長輩 16 筆記憶）：長輩原話那路 839ms（embed 302＋vector 518，
# 加總即全部），本路 1808ms——多出的 994ms 全在 entity boost。兩路是並行的，總耗時
# 由慢的那路決定，故這個空格讓整個長期記憶檢索從 0.84s 變成 1.8s。
# 改寫後實測 1466ms → 701ms，且撈回的記憶與改寫前完全相同。
# 由 `test_health_query_does_not_trigger_mem0_entity_boost` 守住。
HEALTH_QUERY = "最近的用藥、慢性病、過敏與回診等健康狀況"


class LongTermStore(Protocol):
    def add(
        self,
        elder_id: str,
        messages: list[Message],
        *,
        provenance: str = "self_claimed",
        occurred_on: str | None = None,
    ) -> None: ...
    def search(
        self, elder_id: str, query: str, *, top_k: int | None = None
    ) -> list[MemoryItem]: ...
    def list_for_elder(self, elder_id: str, *, limit: int = 50) -> list[MemoryItem]: ...


def _created_at(item: dict) -> str:
    """取出 mem0 item 的 created_at（ISO 字串）；缺值或非字串回空字串。

    ⚠️ 這是**寫入時刻**，不是對話發生日：整理批次凌晨 3 點跑、寫的是昨天的對話，
    故 created_at 恆比內容晚一天（補整理批次更可差多天）。要對話日請用 `_occurred_on`。
    """
    value = item.get("created_at") or (item.get("metadata") or {}).get("created_at")
    return value if isinstance(value, str) else ""


def _occurred_on(item: dict) -> str:
    """這筆記憶「講的是哪一天」（YYYY-MM-DD）。

    優先取 consolidation 存進 metadata 的對話日；舊資料沒有這個欄位，退回
    created_at 的日期部分——即本欄位存在之前的（晚一天的）行為。刻意不回推
    「created_at 減一天」：補整理批次會在同一時刻寫入多個不同的對話日，減一天
    對它們是錯的，寧可沿用舊值也不換成另一個錯的值。
    """
    occurred = (item.get("metadata") or {}).get("occurred_on")
    if isinstance(occurred, str) and occurred:
        return occurred
    return _created_at(item)[:10]  # ISO-8601 前 10 碼即 YYYY-MM-DD


def _recency_key(item: dict) -> tuple[str, str]:
    """排序鍵：先對話日、再寫入時刻（同日多筆時定序）。

    只用 created_at 不夠：停機補整理（庚-06）會把多個對話日在同一秒寫入，
    寫入序與對話序無關。prompt 明著跟模型說記憶「已由新到舊排列」，排錯＝騙它。
    舊資料兩者同源（date 即 created_at 前 10 碼），排序結果與本函式引入前一致。
    """
    return (_occurred_on(item), _created_at(item))


def _to_memory_item(item: dict) -> MemoryItem:
    """把 mem0 raw dict 轉為結構化 MemoryItem（來源解析為標籤、日期取對話日）。"""
    text = item.get("memory") or item.get("text") or ""
    src = (item.get("metadata") or {}).get("provenance")
    return MemoryItem(
        text=text,
        provenance=prov.label(src) if src else "",
        date=_occurred_on(item),
    )


class Mem0LongTermStore:
    def __init__(self, memory, *, top_k: int = 5, health_top_k: int = 3) -> None:
        self._memory = memory
        self._top_k = top_k
        self._health_top_k = health_top_k

    @tracing.track(name="mem0_add", type="general", capture_input=False, capture_output=False)
    def add(
        self,
        elder_id: str,
        messages: list[Message],
        *,
        provenance: str = prov.SELF_CLAIMED,
        occurred_on: str | None = None,
    ) -> None:
        """occurred_on＝這批對話發生的那一天（YYYY-MM-DD）。

        非給不可：mem0 的 created_at 記的是寫入時刻，而整理批次凌晨 3 點寫的是
        昨天的對話——對話日只有呼叫端知道（spec 2026-07-17）。
        """
        payload = [{"role": m.role, "content": m.content} for m in messages]
        metadata = {"provenance": provenance}
        if occurred_on:
            metadata["occurred_on"] = occurred_on
        # 寫入的對話與出處攤在本層 span（span I/O，非 capture——首參 self 是 mem0 client）。
        tracing.set_current_span_io(span_input={"messages": payload, "metadata": metadata})
        # mem0 內部抽取事實用的 prompt（config 層設定）也註冊/連結，供版本追蹤。
        tracing.attach_prompt("mem0_fact_extraction", prov.CUSTOM_FACT_EXTRACTION_PROMPT)
        self._memory.add(payload, user_id=elder_id, metadata=metadata)

    # 逐路一顆 span（2026-07-30 spec）：兩路並行時 waterfall 才分得出原話／健康
    # 增補各自的耗時；input 的 query 即可辨路。output 關——合併結果已由外層
    # mem0_search 捕捉，重複攤一份只是燒儲存。
    @tracing.track(name="mem0_search_raw", capture_input=True, capture_output=False)
    def _search_raw(self, query: str, elder_id: str, top_k: int) -> list[dict]:
        try:
            # rerank＋explain（✅ D-40 丁-4）：reranker 是否生效由 mem0 config 決定
            # （LONGTERM_RERANK_ENABLED），未配置時 mem0 自動略過；explain 附評分細節。
            result = self._memory.search(
                query, filters={"user_id": elder_id}, top_k=top_k, rerank=True, explain=True
            )
        except Exception as exc:  # noqa: BLE001 — 記憶壞掉不可中斷對話
            logger.warning("長期記憶檢索失敗，退化為無記憶：%s", exc)
            return []
        if isinstance(result, dict):
            return result.get("results") or []
        return result or []

    @staticmethod
    def _dedup(items: list[dict]) -> list[dict]:
        seen = set()
        out = []
        for item in items:
            key = item.get("id") or item.get("memory") or item.get("text")
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def list_for_elder(self, elder_id: str, *, limit: int = 50) -> list[MemoryItem]:
        """列出某長輩全部長期記憶（admin 觀測用），由新到舊；取失敗回空清單。"""
        try:
            result = self._memory.get_all(filters={"user_id": elder_id}, limit=limit)
        except Exception as exc:  # noqa: BLE001 — 觀測讀取失敗不可影響服務
            logger.warning("長期記憶列表失敗 elder=%s：%s", elder_id, exc)
            return []
        items = (result.get("results") or []) if isinstance(result, dict) else (result or [])
        ordered = sorted(items, key=_recency_key, reverse=True)
        return [item for item in map(_to_memory_item, ordered) if item.text]

    @tracing.track(name="mem0_search", type="general", capture_input=True, capture_output=True)
    def search(self, elder_id: str, query: str, *, top_k: int | None = None) -> list[MemoryItem]:
        """長輩原話與健康增補**並行**檢索（2026-07-26 延遲實測）。

        每次 `_search_raw` 都是「embedding API ＋ 向量查詢 ＋（視設定）LLM rerank」，
        實測合計約 2.3 秒；兩次排隊跑就是 4.6 秒，佔端到端延遲近三成。兩個查詢彼此
        無依賴（一個用長輩原話、一個用固定的健康關鍵字），沒有理由排隊。

        ⚠️ 合併順序維持「先 user、後 health」不可交換：`_dedup` 保留先出現者，兩邊
        撈到同一筆記憶時，該留下的是**依長輩原話**檢索出來的那筆。並行只改變兩者
        何時發出，不改變合併與排序（`test_search_dedups_overlapping_id` 守住）。

        `_search_raw` 自帶 fail-safe（檢索失敗回空清單、不上拋），故兩邊各自的失敗
        互不影響——`test_health_search_failure_keeps_user_results` 守住這條。
        """
        contexts = [contextvars.copy_context() for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            user_future = pool.submit(
                contexts[0].run, self._search_raw, query, elder_id, top_k or self._top_k
            )
            health_future = pool.submit(
                contexts[1].run, self._search_raw, HEALTH_QUERY, elder_id, self._health_top_k
            )
            user_items, health_items = user_future.result(), health_future.result()
        merged = self._dedup(user_items + health_items)
        for item in merged:
            # explain 供檢索調校：⚠️ score_details 可能含記憶原文，故只走 DEBUG。
            # 正式環境的 root level 是 INFO（logging_setup），這行不會出現在 logs/；
            # **不可為了除錯把正式環境調成 DEBUG**——對話內容只進 Opik（2026-07-27 政策）。
            if "score_details" in item:
                logger.debug("記憶評分 %s：%s", item.get("id"), item.get("score_details"))
        # 由新到舊：對話日遞減（同日再比寫入時刻）；兩者皆缺者排最後。
        ordered = sorted(merged, key=_recency_key, reverse=True)
        return [item for item in map(_to_memory_item, ordered) if item.text]
