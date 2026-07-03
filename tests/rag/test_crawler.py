from datetime import datetime

from kinsun.rag.crawler import CrawlerConfig, FetchedPage, HealthEducationCrawler
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
