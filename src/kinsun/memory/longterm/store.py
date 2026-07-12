"""長期記憶薄介面：把 Mem0 包在自有 Protocol 後，供 agent／consolidation 使用。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.llm import Message
from kinsun.memory.longterm import provenance as prov
from kinsun.memory.models import MemoryItem

logger = logging.getLogger(__name__)

# 每輪固定增補檢索：讓用藥/慢性病等穩定健康事實即使與當下話題無關也浮現。
HEALTH_QUERY = "用藥 慢性病 過敏 回診 健康狀況"


class LongTermStore(Protocol):
    def add(
        self, elder_id: str, messages: list[Message], *, provenance: str = "self_claimed"
    ) -> None: ...
    def search(self, elder_id: str, query: str, *, top_k: int = 5) -> list[MemoryItem]: ...


def _created_at(item: dict) -> str:
    """取出 mem0 item 的 created_at（ISO 字串）；缺值或非字串回空字串。"""
    value = item.get("created_at") or (item.get("metadata") or {}).get("created_at")
    return value if isinstance(value, str) else ""


def _to_memory_item(item: dict) -> MemoryItem:
    """把 mem0 raw dict 轉為結構化 MemoryItem（來源解析為標籤、日期取 YYYY-MM-DD）。"""
    text = item.get("memory") or item.get("text") or ""
    src = (item.get("metadata") or {}).get("provenance")
    created_at = _created_at(item)
    return MemoryItem(
        text=text,
        provenance=prov.label(src) if src else "",
        date=created_at[:10] if created_at else "",  # ISO-8601 前 10 碼即 YYYY-MM-DD
    )


class Mem0LongTermStore:
    def __init__(self, memory, *, top_k: int = 5, health_top_k: int = 3) -> None:
        self._memory = memory
        self._top_k = top_k
        self._health_top_k = health_top_k

    def add(
        self, elder_id: str, messages: list[Message], *, provenance: str = prov.SELF_CLAIMED
    ) -> None:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        self._memory.add(payload, user_id=elder_id, metadata={"provenance": provenance})

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

    def search(self, elder_id: str, query: str, *, top_k: int | None = None) -> list[MemoryItem]:
        user_items = self._search_raw(query, elder_id, top_k or self._top_k)
        health_items = self._search_raw(HEALTH_QUERY, elder_id, self._health_top_k)
        merged = self._dedup(user_items + health_items)
        for item in merged:
            if "score_details" in item:  # explain 供調閱：debug 層記錄，不進 prompt
                logger.debug("記憶評分 %s：%s", item.get("id"), item.get("score_details"))
        # 由新到舊：created_at 遞減；缺 created_at 者排最後（與原排版排序一致）。
        ordered = sorted(merged, key=_created_at, reverse=True)
        return [item for item in map(_to_memory_item, ordered) if item.text]
