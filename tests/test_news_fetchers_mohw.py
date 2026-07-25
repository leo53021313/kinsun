from __future__ import annotations

from datetime import UTC, datetime

from kinsun.news.fetchers.mohw import MohwNewsFetcher, _parse_roc_date
from kinsun.transport import FakeTransport, Response

_LIST_HTML = (
    '<html><body><section class="list"><ul>'
    '<li><a href="https://www.mohw.gov.tw/cp-16-1-1.html" title="測試新聞標題">'
    "<p>測試新聞標題</p><time>115-07-20</time></a></li>"
    "</ul></section></body></html>"
)

_DETAIL_HTML = (
    '<html><body><section class="cp"><article><div>這是新聞內文。</div></article>'
    "</section></body></html>"
)


def _handler(method: str, url: str, data: bytes | None) -> Response:
    if url == "https://www.mohw.gov.tw/lp-16-1.html":
        return Response(200, {}, _LIST_HTML.encode("utf-8"))
    if url == "https://www.mohw.gov.tw/cp-16-1-1.html":
        return Response(200, {}, _DETAIL_HTML.encode("utf-8"))
    return Response(404, {}, b"")


def test_parse_roc_date_converts_to_gregorian_epoch():
    ts = _parse_roc_date("115-07-20")
    assert ts is not None
    dt = datetime.fromtimestamp(ts, tz=UTC)
    assert (dt.year, dt.month, dt.day) == (2026, 7, 20)


def test_parse_roc_date_returns_none_for_malformed_input():
    assert _parse_roc_date("not-a-date") is None


def test_fetch_returns_items_with_title_url_and_content():
    transport = FakeTransport(handler=_handler)
    fetcher = MohwNewsFetcher(clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport)
    items = fetcher.fetch()
    assert len(items) == 1
    item = items[0]
    assert item.title == "測試新聞標題"
    assert item.url == "https://www.mohw.gov.tw/cp-16-1-1.html"
    assert item.source_id == "mohw"
    assert "這是新聞內文" in item.content
    assert item.published_at == _parse_roc_date("115-07-20")


def test_fetch_id_is_deterministic_across_calls():
    transport = FakeTransport(handler=_handler)
    fetcher = MohwNewsFetcher(clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport)
    first = fetcher.fetch()[0].news_item_id
    second = fetcher.fetch()[0].news_item_id
    assert first == second


def test_fetch_skips_page_gracefully_when_list_request_fails():
    transport = FakeTransport(handler=lambda m, u, d: Response(500, {}, b""))
    fetcher = MohwNewsFetcher(clock=lambda: datetime(2026, 7, 20, tzinfo=UTC), transport=transport)
    assert fetcher.fetch() == []
