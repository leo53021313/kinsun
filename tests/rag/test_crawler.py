from datetime import datetime

import pytest

from kinsun.rag.crawler import (
    CrawlerConfig,
    DomainParserRegistry,
    FetchedPage,
    HealthEducationCrawler,
)
from kinsun.rag.source_registry import SourceRegistry


def _page(url: str, html: str) -> FetchedPage:
    return FetchedPage(
        url=url,
        content_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
        fetched_at=datetime(2026, 6, 30),
    )


def test_crawler_extracts_text_links_and_stays_in_allowlist():
    source = SourceRegistry().get("hpa_elder_health")
    pages = {
        source.url: _page(
            source.url,
            """
            <html><head><title>銀髮族健康</title></head>
            <body><nav>略過</nav><main>長者高血壓衛教 2026-06-30</main>
            <a href="/Pages/Detail.aspx?nodeid=39&pid=1">下一頁</a>
            <a href="https://evil.example/x">外部</a></body></html>
            """,
        ),
        "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1": _page(
            "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1",
            "<html><body>飲食和運動衛教</body></html>",
        ),
    }

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=5, delay_seconds=0),
        fetcher=lambda url: pages[url],
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    assert len(result.pages) == 2
    assert "長者高血壓衛教" in result.pages[0].text
    assert result.pages[0].published_at.isoformat() == "2026-06-30"
    assert result.skipped_urls == ()


def test_crawler_records_page_failure_without_stopping_batch():
    source = SourceRegistry().get("hpa_elder_health")

    def fetcher(url):
        if url == source.url:
            return _page(source.url, '<html><body>首頁<a href="/bad">壞頁</a></body></html>')
        raise RuntimeError("boom")

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=3, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    assert len(result.pages) == 1
    assert result.failed_urls == (("https://www.hpa.gov.tw/bad", "boom"),)


def test_html_parser_prefers_main_and_preserves_paragraph_boundaries():
    source = SourceRegistry().get("hpa_elder_health")
    page = _page(
        source.url,
        "<html><body><div>外層廣告</div><main><p>第一段。</p><p>第二段。</p></main></body></html>",
    )

    parsed = DomainParserRegistry().parse(page, source)

    assert parsed.text == "第一段。\n第二段。"
    assert "外層廣告" not in parsed.text


def test_html_parser_extracts_content_inside_webforms_form_wrapper():
    """ASP.NET WebForms（如 hpa.gov.tw）整頁包在 <form> 內，內文不可因此被跳過。"""
    source = SourceRegistry().get("hpa_elder_health")
    page = _page(
        source.url,
        "<html><head><title>國健署</title></head><body>"
        '<form name="aspnetForm" method="post">'
        "<nav>選單</nav>"
        "<div><p>長者高血壓照護重點。</p></div>"
        "<select><option>年份</option></select>"
        "<button>查詢</button>"
        "</form></body></html>",
    )

    parsed = DomainParserRegistry().parse(page, source)

    assert "長者高血壓照護重點" in parsed.text
    assert "年份" not in parsed.text
    assert "查詢" not in parsed.text


def test_json_and_rss_are_parsed_as_discovery_records():
    source = SourceRegistry().get("hpa_news_api")
    parser = DomainParserRegistry()
    json_page = FetchedPage(
        source.url,
        "application/json",
        b'{"title":"health update","url":"https://www.hpa.gov.tw/new"}',
        datetime(2026, 6, 30),
    )
    rss_page = FetchedPage(
        "https://www.hpa.gov.tw/feed.xml",
        "application/rss+xml",
        b"<rss><channel><title>health feed</title><link>https://www.hpa.gov.tw/a</link></channel></rss>",
        datetime(2026, 6, 30),
    )

    parsed_json = parser.parse(json_page, source)
    parsed_rss = parser.parse(rss_page, source)

    assert parsed_json.parser_used.startswith("json:")
    assert parsed_json.links == ("https://www.hpa.gov.tw/new",)
    assert parsed_rss.parser_used.startswith("xml:")
    assert parsed_rss.links == ("https://www.hpa.gov.tw/a",)


def test_text_pdf_is_parsed_and_scanned_pdf_is_skipped(monkeypatch):
    source = SourceRegistry().get("hpa_handbooks")
    page = FetchedPage(
        "https://www.hpa.gov.tw/book.pdf",
        "application/pdf",
        b"fake-pdf",
        datetime(2026, 6, 30),
    )
    parser = DomainParserRegistry()
    monkeypatch.setattr("kinsun.rag.crawler._extract_pdf_text", lambda body: "長者運動衛教。")
    assert parser.parse(page, source).text == "長者運動衛教。"

    monkeypatch.setattr("kinsun.rag.crawler._extract_pdf_text", lambda body: "")
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=1, delay_seconds=0),
        fetcher=lambda url: page,
        sleeper=lambda seconds: None,
    )
    result = crawler.crawl_urls(source, (page.url,))
    assert result.pages == ()
    assert result.skipped_urls == (page.url,)


class _FakeUrlopenResponse:
    """模擬 urllib.request.urlopen 的 context-manager 回應。"""

    def __init__(self, *, url: str, body: bytes, content_type: str = "text/html") -> None:
        self._url = url
        self._body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def geturl(self) -> str:
        return self._url

    def read(self) -> bytes:
        return self._body


def test_fetch_retries_transient_failure_then_succeeds(monkeypatch):
    """_fetch 對可暫時性失敗會重試，成功前每次失敗睡一次 delay_seconds。"""
    attempts = {"n": 0}

    def fake_urlopen(request, timeout):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("暫時性連線失敗")
        return _FakeUrlopenResponse(url="https://www.hpa.gov.tw/a", body=b"<html>ok</html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sleeps: list[float] = []
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(retries=2, delay_seconds=0.5),
        sleeper=sleeps.append,
    )

    page = crawler._fetch("https://www.hpa.gov.tw/a")

    assert page.body == b"<html>ok</html>"
    assert attempts["n"] == 2
    # 三次嘗試上限內、第二次成功：兩次嘗試之間睡一次。
    assert sleeps == [0.5]


def test_fetch_raises_runtime_error_after_exhausting_retries(monkeypatch):
    """_fetch 重試耗盡後翻成 RuntimeError（保留最後一個錯誤訊息）。"""

    def always_fail(request, timeout):
        raise OSError("boom")

    monkeypatch.setattr("urllib.request.urlopen", always_fail)
    sleeps: list[float] = []
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(retries=2, delay_seconds=0.5),
        sleeper=sleeps.append,
    )

    with pytest.raises(RuntimeError, match="boom"):
        crawler._fetch("https://www.hpa.gov.tw/x")

    # retries+1=3 次嘗試、之間睡兩次；最後一次失敗後不再多睡（tenacity 語意）。
    assert sleeps == [0.5, 0.5]
