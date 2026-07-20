"""長期記憶薄介面：把 Mem0 包在自有 Protocol 後，供 agent／consolidation 使用。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.longterm import provenance as prov
from kinsun.memory.models import MemoryItem

logger = logging.getLogger(__name__)

# 每輪固定增補檢索：讓用藥/慢性病等穩定健康事實即使與當下話題無關也浮現。
HEALTH_QUERY = "用藥 慢性病 過敏 回診 健康狀況"


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
        self._memory.add(payload, user_id=elder_id, metadata=metadata)

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
        user_items = self._search_raw(query, elder_id, top_k or self._top_k)
        health_items = self._search_raw(HEALTH_QUERY, elder_id, self._health_top_k)
        merged = self._dedup(user_items + health_items)
        for item in merged:
            if "score_details" in item:  # explain 供調閱：debug 層記錄，不進 prompt
                logger.debug("記憶評分 %s：%s", item.get("id"), item.get("score_details"))
        # 由新到舊：對話日遞減（同日再比寫入時刻）；兩者皆缺者排最後。
        ordered = sorted(merged, key=_recency_key, reverse=True)
        return [item for item in map(_to_memory_item, ordered) if item.text]
