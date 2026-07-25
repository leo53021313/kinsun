from __future__ import annotations

from datetime import UTC, datetime

from kinsun.news.models import NewsItem
from kinsun.news.store import FakeNewsStore, NewsError
from kinsun.tools.news import NEWS_SPEC, build_news_handler

_NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)


def _clock() -> datetime:
    return _NOW


def _item(news_item_id: str, *, title: str, retrieved_at: float, publisher: str = "衛生福利部"):
    return NewsItem(
        news_item_id=news_item_id,
        source_id="mohw",
        title=title,
        url=f"https://example.com/{news_item_id}",
        publisher=publisher,
        content="內文",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
    )


def test_spec_has_name_and_no_parameters():
    assert NEWS_SPEC.name == "get_news"
    assert NEWS_SPEC.parameters == {"type": "object", "properties": {}}


def test_handler_returns_recent_titles_with_publisher():
    store = FakeNewsStore()
    store.save(_item("n1", title="長者防跌新措施", retrieved_at=_NOW.timestamp() - 3600))
    store.save(
        _item(
            "n2", title="流感疫苗開打", retrieved_at=_NOW.timestamp() - 7200, publisher="測試媒體"
        )
    )
    handler = build_news_handler(store, clock=_clock)
    reply = handler({})
    assert "長者防跌新措施" in reply
    assert "流感疫苗開打" in reply
    assert "衛生福利部" in reply
    assert "測試媒體" in reply


def test_handler_limits_to_five_titles():
    store = FakeNewsStore()
    for i in range(6):
        store.save(_item(f"n{i}", title=f"新聞{i}", retrieved_at=_NOW.timestamp() - i))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({})
    # retrieved_at 最新的前五則（n0..n4）保留，最舊的 n5 被截掉
    assert "新聞4" in reply
    assert "新聞5" not in reply


def test_handler_excludes_items_older_than_window():
    store = FakeNewsStore()
    store.save(_item("old", title="四天前的舊聞", retrieved_at=_NOW.timestamp() - 4 * 86400))
    store.save(_item("new", title="今天的新聞", retrieved_at=_NOW.timestamp() - 3600))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({})
    assert "今天的新聞" in reply
    assert "四天前的舊聞" not in reply


def test_handler_returns_friendly_message_when_empty():
    handler = build_news_handler(FakeNewsStore(), clock=_clock)
    assert handler({}) == "目前沒有最新的新聞資料，晚一點再問問我。"


def test_handler_degrades_to_friendly_message_on_store_failure():
    class _ExplodingStore(FakeNewsStore):
        def list_recent(self, *, since):
            raise NewsError("news_items 表掛了")

    handler = build_news_handler(_ExplodingStore(), clock=_clock)
    assert handler({}) == "（新聞資料暫時讀不到，請稍後再試）"
