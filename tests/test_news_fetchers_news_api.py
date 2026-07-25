from __future__ import annotations

import json
from datetime import UTC, datetime

from kinsun.news.fetchers.news_api import NewsApiFetcher
from kinsun.transport import FakeTransport, Response, TransportError

_BODY = json.dumps(
    {
        "totalResults": 1,
        "articles": [
            {
                "title": "測試新聞",
                "source": {"name": "測試媒體"},
                "url": "https://example.com/a1",
                "publishedAt": "2026-07-19T14:15:00Z",
                "description": "摘要內容",
            }
        ],
    }
).encode("utf-8")


def test_fetch_maps_articles_to_news_items():
    transport = FakeTransport(responses=[Response(200, {}, _BODY)])
    fetcher = NewsApiFetcher(
        api_key="key123", clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport
    )
    items = fetcher.fetch()
    assert len(items) == 1
    item = items[0]
    assert item.title == "測試新聞"
    assert item.publisher == "測試媒體"
    assert item.url == "https://example.com/a1"
    assert item.content == "摘要內容"
    assert item.source_id == "news_api"
    # apiKey 有帶進請求 URL
    assert "apiKey=key123" in transport.calls[0][1]


def test_fetch_skips_articles_without_url():
    body = json.dumps({"articles": [{"title": "沒有連結"}]}).encode("utf-8")
    transport = FakeTransport(responses=[Response(200, {}, body)])
    fetcher = NewsApiFetcher(
        api_key="key123", clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport
    )
    assert fetcher.fetch() == []


def test_fetch_returns_empty_list_on_transport_failure():
    transport = FakeTransport()
    transport.error = TransportError("boom")
    fetcher = NewsApiFetcher(
        api_key="key123", clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport
    )
    assert fetcher.fetch() == []
