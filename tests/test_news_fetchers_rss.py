from __future__ import annotations

from datetime import UTC, datetime

from kinsun.news.fetchers.rss import RssNewsFetcher
from kinsun.transport import FakeTransport, Response

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Google 新聞</title>
  <item>
    <title>紅霞颱風暴風圈再擴大 - 自由時報</title>
    <link>https://news.google.com/rss/articles/abc123</link>
    <pubDate>Fri, 24 Jul 2026 22:17:00 GMT</pubDate>
    <source url="https://www.ltn.com.tw">自由時報</source>
    <description>&lt;a href="https://news.google.com/rss/articles/abc123"&gt;紅霞颱風暴風圈再擴大&lt;/a&gt;</description>
  </item>
  <item>
    <title>王功漁火節登場</title>
    <link>https://news.google.com/rss/articles/def456</link>
    <pubDate>Sat, 25 Jul 2026 01:59:00 GMT</pubDate>
    <description>彰化王功漁火節結合音樂美食登場。</description>
  </item>
  <item>
    <title></title>
    <link>https://news.google.com/rss/articles/no-title</link>
    <pubDate>Sat, 25 Jul 2026 02:00:00 GMT</pubDate>
  </item>
  <item>
    <title>沒有連結的項目</title>
    <pubDate>Sat, 25 Jul 2026 02:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def _clock() -> datetime:
    return datetime(2026, 7, 25, 10, 0, tzinfo=UTC)


def _fetcher(transport: FakeTransport) -> RssNewsFetcher:
    return RssNewsFetcher(
        feed_url="https://news.google.com/rss?hl=zh-TW", clock=_clock, transport=transport
    )


def test_fetch_parses_items_with_per_item_source_as_publisher():
    transport = FakeTransport(responses=[Response(200, {}, _FEED_XML.encode("utf-8"))])
    items = _fetcher(transport).fetch()
    first = items[0]
    # Google News 標題帶「 - 媒體名」尾綴：去掉尾綴、媒體名取 <source>。
    assert first.title == "紅霞颱風暴風圈再擴大"
    assert first.publisher == "自由時報"
    assert first.source_id == "rss"
    assert first.url == "https://news.google.com/rss/articles/abc123"
    assert first.retrieved_at == _clock().timestamp()


def test_fetch_falls_back_to_channel_title_when_item_has_no_source():
    transport = FakeTransport(responses=[Response(200, {}, _FEED_XML.encode("utf-8"))])
    second = _fetcher(transport).fetch()[1]
    assert second.publisher == "Google 新聞"
    assert second.title == "王功漁火節登場"
    # description 的 HTML 標籤要剝掉當內文；無 HTML 則原樣。
    assert second.content == "彰化王功漁火節結合音樂美食登場。"


def test_fetch_parses_rfc822_pubdate_to_epoch():
    transport = FakeTransport(responses=[Response(200, {}, _FEED_XML.encode("utf-8"))])
    first = _fetcher(transport).fetch()[0]
    assert first.published_at is not None
    got = datetime.fromtimestamp(first.published_at, UTC)
    assert (got.month, got.day, got.hour) == (7, 24, 22)


def test_fetch_strips_html_from_description():
    transport = FakeTransport(responses=[Response(200, {}, _FEED_XML.encode("utf-8"))])
    first = _fetcher(transport).fetch()[0]
    assert "<" not in first.content
    assert "紅霞颱風暴風圈再擴大" in first.content


def test_fetch_skips_items_without_title_or_link():
    transport = FakeTransport(responses=[Response(200, {}, _FEED_XML.encode("utf-8"))])
    items = _fetcher(transport).fetch()
    assert len(items) == 2  # 空標題與缺連結的兩筆都跳過


def test_fetch_returns_empty_on_http_error():
    transport = FakeTransport(responses=[Response(500, {}, b"")])
    assert _fetcher(transport).fetch() == []


def test_fetch_returns_empty_on_malformed_xml():
    transport = FakeTransport(responses=[Response(200, {}, "不是 XML".encode())])
    assert _fetcher(transport).fetch() == []
