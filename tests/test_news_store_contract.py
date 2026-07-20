"""NewsStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言以 `ns` 前綴 scope 到本測試
自己的資料，才能在共用真庫上互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.news.models import NewsItem
from kinsun.news.store import FakeNewsStore, PgNewsStore


def _item(news_item_id: str, *, retrieved_at: float, title: str = "標題") -> NewsItem:
    return NewsItem(
        news_item_id=news_item_id,
        source_id="mohw",
        title=title,
        url=f"https://example.com/{news_item_id}",
        publisher="衛生福利部",
        content="內文",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
    )


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgNewsStore(request.getfixturevalue("pg_database"))
    return FakeNewsStore()


def test_list_recent_only_returns_items_since_cutoff(store, ns):
    store.save(_item(f"{ns}old", retrieved_at=100.0))
    store.save(_item(f"{ns}new", retrieved_at=200.0))
    ids = {i.news_item_id for i in store.list_recent(since=150.0)}
    assert f"{ns}new" in ids
    assert f"{ns}old" not in ids


def test_save_upserts_on_conflict(store, ns):
    store.save(_item(f"{ns}a1", retrieved_at=100.0, title="原標題"))
    store.save(_item(f"{ns}a1", retrieved_at=200.0, title="改標題"))
    got = [i for i in store.list_recent(since=0.0) if i.news_item_id == f"{ns}a1"]
    assert len(got) == 1
    assert got[0].title == "改標題"
    assert got[0].retrieved_at == 200.0


def test_purge_older_than_removes_only_expired(store, ns):
    store.save(_item(f"{ns}old", retrieved_at=100.0))
    store.save(_item(f"{ns}new", retrieved_at=200.0))
    store.purge_older_than(150.0)
    ids = {i.news_item_id for i in store.list_recent(since=0.0)}
    assert f"{ns}old" not in ids
    assert f"{ns}new" in ids
