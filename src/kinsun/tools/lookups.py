"""上網查證來源紀錄持久化：append-only 流水帳，供日後追查金孫引用了哪些網頁。

金孫回覆長輩時只口語帶一句來源（「衛福部網站說…」），完整網址不唸出來；本表把每次
查詢的關鍵字、主題與來源清單留痕，日後要查證引用出處時看這裡。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from psycopg.types.json import Json

from kinsun.db import Database, _Errors

logger = logging.getLogger("kinsun.tools.lookups")

# 查詢結果狀態：ok＝有結果、empty＝白名單內查無、error＝搜尋服務失敗。
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class WebSearchLookup:
    web_search_lookup_id: str
    query: str
    topic: str
    status: str
    sources: list[dict]
    created_at: float


class WebSearchLookupError(Exception):
    """上網查證紀錄讀寫失敗。"""


class WebSearchLookupStore(Protocol):
    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None: ...
    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]: ...


class PgWebSearchLookupStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: WebSearchLookupError(f"上網查證紀錄存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None:
        self._db.execute(
            "INSERT INTO web_search_lookups "
            "(web_search_lookup_id, query, topic, status, sources, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (self._new_id(), query, topic, status, Json(sources), self._clock().timestamp()),
        )

    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]:
        rows = self._db.query(
            "SELECT web_search_lookup_id, query, topic, status, sources, created_at "
            "FROM web_search_lookups ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        return [WebSearchLookup(*row) for row in rows]


class FakeWebSearchLookupStore:
    """WebSearchLookupStore 的記憶體替身（測試用，不碰 DB）。

    web_search_lookup_id 與 created_at 由附加順序虛構、僅供排序，因此合約只斷言雙方都會
    產生的欄位。回傳由新到舊，對齊 PgWebSearchLookupStore 的 ORDER BY created_at DESC。
    """

    def __init__(self) -> None:
        self.recorded: list[tuple[str, str, str, list[dict]]] = []

    def record(self, *, query: str, topic: str, status: str, sources: list[dict]) -> None:
        self.recorded.append((query, topic, status, list(sources)))

    def list_recent(self, limit: int = 50) -> list[WebSearchLookup]:
        lookups = [
            WebSearchLookup(str(i), query, topic, status, sources, float(i))
            for i, (query, topic, status, sources) in enumerate(self.recorded)
        ]
        return sorted(lookups, key=lambda lookup: lookup.created_at, reverse=True)[:limit]


def safe_record(
    lookups: WebSearchLookupStore | None,
    *,
    query: str,
    topic: str,
    status: str,
    sources: list[dict],
) -> None:
    """留痕失敗絕不中斷對話：吞掉所有例外、只留 warning。"""
    if lookups is None:
        return
    try:
        lookups.record(query=query, topic=topic, status=status, sources=sources)
    except Exception:  # noqa: BLE001 - 觀測記錄失敗不可影響主流程
        logger.warning("上網查證紀錄落庫失敗", exc_info=True)
