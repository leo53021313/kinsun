from datetime import datetime

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
