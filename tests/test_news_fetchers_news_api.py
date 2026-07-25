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
    # 金鑰走 X-Api-Key header、不進 URL（D-74 後續③：URL 會進 TransportError 訊息與 log）
    method, url, _data, headers, _timeout = transport.calls[0]
    assert headers.get("X-Api-Key") == "key123"
    assert "key123" not in url


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


_MIXED_BODY = json.dumps(
    {
        "articles": [
            {
                "title": "台灣好新聞",
                "source": {"name": "Yahoo奇摩新聞"},
                "url": "https://tw.news.yahoo.com/a1",
                "publishedAt": "2026-07-19T14:15:00Z",
                "description": "繁體內容",
            },
            {
                "title": "香港新聞",
                "source": {"name": "Yahoo HK"},
                "url": "https://hk.news.yahoo.com/a2",
                "publishedAt": "2026-07-19T14:00:00Z",
                "description": "港版內容",
            },
            {
                "title": "中國科技站",
                "source": {"name": "cnBeta"},
                "url": "https://www.cnbeta.com.tw/a3",
                "publishedAt": "2026-07-19T13:00:00Z",
                "description": "簡體內容",
            },
        ]
    }
).encode("utf-8")


def test_fetch_keeps_only_allowlisted_hosts():
    # 台灣來源白名單改「抓回後按文章網址過濾」（Leo 2026-07-25：不要大陸／中國來源）：
    # 實測 News API 的 domains 參數只認基底網域（yahoo.com 全球一鍋、台灣本土媒體
    # 完全沒收錄），伺服器端無法只挑台灣版，故 API 端不帶 domains、客戶端後過濾。
    transport = FakeTransport(responses=[Response(200, {}, _MIXED_BODY)])
    fetcher = NewsApiFetcher(
        api_key="key123",
        clock=lambda: datetime(2026, 7, 20, tzinfo=UTC),
        transport=transport,
        domains="tw.news.yahoo.com",
    )
    items = fetcher.fetch()
    assert [i.title for i in items] == ["台灣好新聞"]
    # API 請求不帶 domains 參數（帶了反而 0 結果）
    assert "domains=" not in transport.calls[0][1]


def test_fetch_allowlist_matches_subdomains_of_entry():
    transport = FakeTransport(responses=[Response(200, {}, _MIXED_BODY)])
    fetcher = NewsApiFetcher(
        api_key="key123",
        clock=lambda: datetime(2026, 7, 20, tzinfo=UTC),
        transport=transport,
        domains="news.yahoo.com",  # 條目為上層網域時，tw.news 與 hk.news 子網域都算命中
    )
    assert [i.title for i in fetcher.fetch()] == ["台灣好新聞", "香港新聞"]


def test_fetch_without_allowlist_keeps_everything():
    transport = FakeTransport(responses=[Response(200, {}, _MIXED_BODY)])
    fetcher = NewsApiFetcher(
        api_key="key123", clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport
    )
    assert len(fetcher.fetch()) == 3
