"""新聞提及紀錄：記「對哪位長輩給過哪則新聞」，供 get_news 不重複給料。

append-only 事件紀錄（`record` 動詞），同一（長輩, 新聞）只留一列；
逾期清除與 news_items 同步（同一把保留天數，見 scheduler/worker.py）。
檔名依語意命名（D-42 例外，比照 safety/deliveries.py），三件套結構不變。
"""

from __future__ import annotations

from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.news.store import NewsError


class NewsMentionStore(Protocol):
    def record(self, elder_id: str, news_item_id: str, *, mentioned_at: float) -> None: ...
    def list_for_elder(self, elder_id: str) -> set[str]: ...
    def purge_older_than(self, cutoff: float) -> None: ...


class PgNewsMentionStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: NewsError(f"新聞提及紀錄存取失敗：{m}"))

    def record(self, elder_id: str, news_item_id: str, *, mentioned_at: float) -> None:
        # DO NOTHING：同一則對同一位長輩重複給料不算新事件，保留首次時間。
        self._db.execute(
            "INSERT INTO news_mentions (elder_id, news_item_id, mentioned_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (elder_id, news_item_id) DO NOTHING",
            (elder_id, news_item_id, mentioned_at),
        )

    def list_for_elder(self, elder_id: str) -> set[str]:
        rows = self._db.query(
            "SELECT news_item_id FROM news_mentions WHERE elder_id = %s", (elder_id,)
        )
        return {row[0] for row in rows}

    def purge_older_than(self, cutoff: float) -> None:
        self._db.execute("DELETE FROM news_mentions WHERE mentioned_at < %s", (cutoff,))


class FakeNewsMentionStore:
    """NewsMentionStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._mentions: dict[tuple[str, str], float] = {}

    def record(self, elder_id: str, news_item_id: str, *, mentioned_at: float) -> None:
        self._mentions.setdefault((elder_id, news_item_id), mentioned_at)

    def list_for_elder(self, elder_id: str) -> set[str]:
        return {news_id for (eid, news_id) in self._mentions if eid == elder_id}

    def purge_older_than(self, cutoff: float) -> None:
        self._mentions = {k: at for k, at in self._mentions.items() if at >= cutoff}
