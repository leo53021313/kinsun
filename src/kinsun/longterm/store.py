"""長期記憶薄介面：把 Mem0 包在自有 Protocol 後，供 agent／consolidation 使用。"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.llm import Message
from kinsun.longterm import provenance as prov

logger = logging.getLogger(__name__)

_PREFIX = "\n以下為這位長者的長期記憶（部分為長者自述、未必經確認，請勿當成醫療診斷）：\n"


class LongTermStore(Protocol):
    def add(
        self, session_id: str, messages: list[Message], *, provenance: str = "self_claimed"
    ) -> None: ...
    def search(self, session_id: str, query: str, *, top_k: int = 5) -> str: ...


def _format_memories_for_prompt(result: dict) -> str:
    items = result.get("results") or []
    if not items:
        return ""
    lines = []
    for item in items:
        text = item.get("memory") or item.get("text") or ""
        if not text:
            continue
        src = (item.get("metadata") or {}).get("provenance")
        suffix = f"（{prov.label(src)}）" if src else ""
        lines.append(f"- {text}{suffix}")
    if not lines:
        return ""
    return _PREFIX + "\n".join(lines) + "\n"


class Mem0LongTermStore:
    def __init__(self, memory, *, top_k: int = 5) -> None:
        self._memory = memory
        self._top_k = top_k

    def add(
        self, session_id: str, messages: list[Message], *, provenance: str = prov.SELF_CLAIMED
    ) -> None:
        payload = [{"role": m.role, "content": m.text} for m in messages]
        self._memory.add(payload, user_id=session_id, metadata={"provenance": provenance})

    def search(self, session_id: str, query: str, *, top_k: int | None = None) -> str:
        try:
            result = self._memory.search(query, user_id=session_id, limit=top_k or self._top_k)
            if not isinstance(result, dict):
                result = {"results": result or []}
            return _format_memories_for_prompt(result)
        except Exception as exc:  # noqa: BLE001 — 記憶壞掉不可中斷對話
            logger.warning("長期記憶檢索失敗，退化為無記憶：%s", exc)
            return ""
