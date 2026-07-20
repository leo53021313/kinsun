"""話題新聞儲存：Protocol、Postgres 實作與測試替身。"""

from __future__ import annotations

from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.news.models import NewsItem


class NewsError(Exception):
    """新聞資料讀寫失敗。"""


class NewsStore(Protocol):
    def save(self, item: NewsItem) -> None: ...
    def list_recent(self, *, since: float) -> list[NewsItem]: ...
    def purge_older_than(self, cutoff: float) -> None: ...


class PgNewsStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: NewsError(f"新聞資料存取失敗：{m}"))

    def _to_item(self, row: tuple) -> NewsItem:
        news_item_id, source_id, title, url, publisher, content, published_at, retrieved_at = row
        return NewsItem(
            news_item_id=news_item_id,
            source_id=source_id,
            title=title,
            url=url,
            publisher=publisher,
            content=content,
            published_at=published_at,
            retrieved_at=retrieved_at,
        )

    def save(self, item: NewsItem) -> None:
        self._db.execute(
            "INSERT INTO news_items (news_item_id, source_id, title, url, publisher, content, "
            "published_at, retrieved_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (news_item_id) DO UPDATE SET "
            "source_id = EXCLUDED.source_id, title = EXCLUDED.title, url = EXCLUDED.url, "
            "publisher = EXCLUDED.publisher, content = EXCLUDED.content, "
            "published_at = EXCLUDED.published_at, retrieved_at = EXCLUDED.retrieved_at",
            (
                item.news_item_id,
                item.source_id,
                item.title,
                item.url,
                item.publisher,
                item.content,
                item.published_at,
                item.retrieved_at,
            ),
        )

    def list_recent(self, *, since: float) -> list[NewsItem]:
        rows = self._db.query(
            "SELECT news_item_id, source_id, title, url, publisher, content, published_at, "
            "retrieved_at FROM news_items WHERE retrieved_at >= %s "
            "ORDER BY retrieved_at DESC",
            (since,),
        )
        return [self._to_item(r) for r in rows]

    def purge_older_than(self, cutoff: float) -> None:
        self._db.execute("DELETE FROM news_items WHERE retrieved_at < %s", (cutoff,))


class FakeNewsStore:
    """NewsStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._items: dict[str, NewsItem] = {}

    def save(self, item: NewsItem) -> None:
        self._items[item.news_item_id] = item

    def list_recent(self, *, since: float) -> list[NewsItem]:
        rows = [i for i in self._items.values() if i.retrieved_at >= since]
        return sorted(rows, key=lambda i: i.retrieved_at, reverse=True)

    def purge_older_than(self, cutoff: float) -> None:
        self._items = {k: v for k, v in self._items.items() if v.retrieved_at >= cutoff}
