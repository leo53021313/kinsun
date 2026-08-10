import urllib.request
from datetime import datetime

import pytest

from kinsun.rag.crawler import (
    CrawlerConfig,
    DomainParserRegistry,
    FetchedPage,
    HealthEducationCrawler,
    HtmlTextExtractor,
    _pdf_title,
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
    from dataclasses import replace

    # 明確測「無內容樣式」的一般爬取路徑（有樣式者只跟隨文章連結，另有專屬測試）
    source = replace(SourceRegistry().get("hpa_elder_health"), content_url_pattern="")

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


def test_json_response_with_html_content_type_is_parsed_as_json():
    """hpa newsapi.ashx 回 JSON 但 Content-Type 標 text/html，須以內容嗅探改走 JSON parser。"""
    source = SourceRegistry().get("hpa_news_api")
    body = (
        '{"newsList":[{"title":"預防熱傷害",'
        '"content":"多喝水 <a href=\\"https://health99.hpa.gov.tw/x\\">詳情</a>",'
        '"url":"https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=1&pid=2"}]}'
    )
    page = FetchedPage(
        url=source.url,
        content_type="text/html",
        body=body.encode("utf-8"),
        fetched_at=datetime(2026, 6, 30),
    )

    parsed = DomainParserRegistry().parse(page, source)

    assert parsed.parser_used.startswith("json:")
    assert "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=1&pid=2" in parsed.links
    assert not any("\\" in link for link in parsed.links)


def test_html_parser_drops_links_with_escaped_quotes():
    """JSON 夾帶的跳脫 href（\\"）不可混進連結清單變成垃圾 URL。"""
    source = SourceRegistry().get("hpa_elder_health")
    page = _page(
        source.url,
        '<html><body><p>內文</p><a href="\\"https://health99.hpa.gov.tw/x\\"">壞連結</a>'
        '<a href="/Pages/ok.aspx">好連結</a></body></html>',
    )

    parsed = DomainParserRegistry().parse(page, source)

    assert any(link.endswith("/Pages/ok.aspx") for link in parsed.links)
    assert not any('"' in link or "\\" in link for link in parsed.links)


def test_crawler_upgrades_followed_http_links_to_https():
    """站內 http:// 舊連結一律升級 https 再抓（hpa 對 http 直接回 403）。"""
    from dataclasses import replace

    source = replace(SourceRegistry().get("hpa_elder_health"), content_url_pattern="")
    pages = {
        source.url: _page(
            source.url,
            '<html><body>首頁 <a href="http://www.hpa.gov.tw/Pages/old.aspx">舊連結</a></body></html>',
        ),
        "https://www.hpa.gov.tw/Pages/old.aspx": _page(
            "https://www.hpa.gov.tw/Pages/old.aspx",
            "<html><body>舊頁內容衛教</body></html>",
        ),
    }

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=5, delay_seconds=0),
        fetcher=lambda url: pages[url],
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    assert len(result.pages) == 2
    assert result.failed_urls == ()


def test_encode_request_url_percent_encodes_non_ascii():
    """URL 含中文（如 file.data.gov.tw 附件）須 percent-encode，且不可重複編碼既有 %XX。"""
    from kinsun.rag.crawler import _encode_request_url

    encoded = _encode_request_url("https://file.data.gov.tw/content/附件3_品質.pdf")
    assert encoded.isascii()
    assert encoded.startswith("https://file.data.gov.tw/content/%E9%99%84%E4%BB%B6")
    assert _encode_request_url("https://a.tw/a%20b?x=1") == "https://a.tw/a%20b?x=1"


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

    def fake_open(request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("暫時性連線失敗")
        return _FakeUrlopenResponse(url="https://www.hpa.gov.tw/a", body=b"<html>ok</html>")

    sleeps: list[float] = []
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(retries=2, delay_seconds=0.5),
        sleeper=sleeps.append,
    )
    monkeypatch.setattr(crawler._opener, "open", fake_open)

    page = crawler._fetch("https://www.hpa.gov.tw/a")

    assert page.body == b"<html>ok</html>"
    assert attempts["n"] == 2
    # 三次嘗試上限內、第二次成功：兩次嘗試之間睡一次。
    assert sleeps == [0.5]


def test_fetch_carries_cookies_across_pages_of_same_source(monkeypatch):
    """health99 先發 session cookie 再轉址回同一網址；不帶 cookie 會被判定為無限轉址。

    2026-07-28 實測：無 cookie 首頁即 302 指向自己（84/85 頁全滅），
    帶 cookie jar 跟隨轉址則 200。cookie 須跨頁沿用，不可每頁重新開瓶。
    """
    seen_jars: list[object] = []

    class _Opener:
        def __init__(self, *handlers):
            seen_jars.extend(
                handler.cookiejar
                for handler in handlers
                if isinstance(handler, urllib.request.HTTPCookieProcessor)
            )

        def open(self, request, timeout=None):
            return _FakeUrlopenResponse(url=request.full_url, body=b"<html>ok</html>")

    monkeypatch.setattr("urllib.request.build_opener", _Opener)
    crawler = HealthEducationCrawler(config=CrawlerConfig(retries=0, delay_seconds=0))

    crawler._fetch("https://health99.hpa.gov.tw/a")
    crawler._fetch("https://health99.hpa.gov.tw/b")

    assert len(seen_jars) == 1, "cookie jar 必須是每個 crawler 一份、跨頁沿用"


def test_fetch_raises_runtime_error_after_exhausting_retries(monkeypatch):
    """_fetch 重試耗盡後翻成 RuntimeError（保留最後一個錯誤訊息）。"""

    def always_fail(request, timeout=None):
        raise OSError("boom")

    sleeps: list[float] = []
    crawler = HealthEducationCrawler(
        config=CrawlerConfig(retries=2, delay_seconds=0.5),
        sleeper=sleeps.append,
    )
    monkeypatch.setattr(crawler._opener, "open", always_fail)

    with pytest.raises(RuntimeError, match="boom"):
        crawler._fetch("https://www.hpa.gov.tw/x")

    # retries+1=3 次嘗試、之間睡兩次；最後一次失敗後不再多睡（tenacity 語意）。
    assert sleeps == [0.5, 0.5]


def test_navigation_links_are_dropped_even_when_they_look_like_articles():
    """導覽／頁尾的連結一律不收，網址型態像文章也不例外。

    ⚠️ 這條測試曾寫成相反的斷言（「導覽區的文章連結必須保留」），依據是
    「hpa 列表頁 37 個 Detail 連結有 29 個在 nav／header／footer」。2026-08-01
    真實網站實測推翻它：放行之後，兩個不同主題的來源抓回一模一樣的 19 篇——
    本署簡介、組織架構圖、各業務服務窗口、本署位置、LINE@頻道……那 29 個是
    每頁都有的機關樣板頁，只是網址剛好也長得像文章。真正的主題文章在內容區。
    """
    from dataclasses import replace

    source = replace(SourceRegistry().get("hpa_elder_health"), content_url_pattern=r"Detail\.aspx")
    page = _page(
        source.url,
        "<html><body>"
        '<nav><a href="/Pages/Detail.aspx?nodeid=10&pid=18">本署簡介</a></nav>'
        '<footer><a href="/Pages/Detail.aspx?nodeid=11&pid=20">各業務服務窗口</a></footer>'
        '<div><p>內文</p><a href="/Pages/Detail.aspx?nodeid=39&pid=99">長者高血壓照護</a></div>'
        "</body></html>",
    )

    parsed = DomainParserRegistry().parse(page, source)

    assert any("pid=99" in link for link in parsed.links), "內容區的文章要收"
    assert not any("pid=18" in link for link in parsed.links), "導覽區的樣板頁不可收"
    assert not any("pid=20" in link for link in parsed.links), "頁尾的樣板頁不可收"


def test_crawler_visits_content_pages_before_navigation_pages():
    """待爬清單先抓文章頁：預算有限時，先花在內容而不是列表與導覽。"""
    from dataclasses import replace

    source = replace(SourceRegistry().get("hpa_elder_health"), content_url_pattern=r"Detail\.aspx")
    pages = {
        source.url: _page(
            source.url,
            "<html><body><div>"
            '<a href="/Pages/List.aspx?nodeid=1">列表一</a>'
            '<a href="/Pages/List.aspx?nodeid=2">列表二</a>'
            '<a href="/Pages/Detail.aspx?nodeid=1&pid=9">文章</a>'
            "</div></body></html>",
        ),
    }
    for path in ("List.aspx?nodeid=1", "List.aspx?nodeid=2", "Detail.aspx?nodeid=1&pid=9"):
        url = f"https://www.hpa.gov.tw/Pages/{path}"
        pages[url] = _page(url, "<html><body><p>內容。</p></body></html>")

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=2, delay_seconds=0),
        fetcher=lambda url: pages[url],
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    assert any("Detail.aspx" in p.url for p in result.pages), "文章頁必須排在列表頁之前被抓到"


def test_content_sources_only_follow_articles_and_treat_them_as_leaves():
    """宣告內容樣式的來源：只跟隨文章連結，且文章不再往外擴。

    2026-08-01 實測：只做「文章優先」還不夠——爬蟲從文章又跳到文章，
    一路漂到菸害防制英文新聞稿、業務服務窗口、統計報告（前 14 篇有 10 篇
    是英文），主題完全不是長輩衛教。列表頁本身就是國健署做好的策展，
    所以只收種子頁列出的文章、文章當葉節點，範圍才守得住。
    """
    from dataclasses import replace

    source = replace(SourceRegistry().get("hpa_elder_health"), content_url_pattern=r"Detail\.aspx")
    article = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1"
    pages = {
        source.url: _page(
            source.url,
            "<html><body><div>"
            f'<a href="{article}">主題文章</a>'
            '<a href="/Pages/List.aspx?nodeid=999">別的列表頁</a>'
            "</div></body></html>",
        ),
        article: _page(
            article,
            "<html><body><p>長者高血壓照護。</p>"
            '<a href="/Pages/Detail.aspx?nodeid=888&pid=9">菸害防制英文新聞稿</a>'
            "</body></html>",
        ),
        # 這兩頁都抓得到——若爬蟲真的跟過去就會出現在結果裡，
        # 不給頁面會讓測試因「抓失敗」而假通過。
        "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=888&pid=9": _page(
            "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=888&pid=9",
            "<html><body><p>Quit smoking for your family.</p></body></html>",
        ),
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=999": _page(
            "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=999",
            "<html><body><p>別的主題列表。</p></body></html>",
        ),
    }

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=10, delay_seconds=0),
        fetcher=lambda url: pages[url],
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    visited = {page.url for page in result.pages}
    assert article in visited, "種子頁列出的文章要收"
    assert not any("nodeid=888" in url for url in visited), "文章是葉節點，不可再往外爬"
    assert any("nodeid=999" in url for url in visited), (
        "內容區的子分類列表要跟隨——文章多半掛在子分類底下，不跟就只剩零星幾篇"
    )


def test_sources_without_content_pattern_keep_following_all_links():
    """未宣告內容樣式的來源仍然跟隨所有連結（既有 discovery 來源仰賴這個）。

    ⚠️ 種子頁只有一個連結、沒有內文，不收成文件是對的（收進去也會被收錄判定
    以「空殼」擋掉），但**連結必須照跟**——不然每個以導覽頁為種子的來源都會
    當場斷頭。2026-08-07 拿掉連結文字後，這條分界才真正被測到。
    """
    source = SourceRegistry().get("mohw_health_window")
    assert source.content_url_pattern == ""
    second = "https://www.mohw.gov.tw/cp-88-1-1.html"
    fetched: list[str] = []
    pages = {
        source.url: _page(source.url, f'<html><body><a href="{second}">下一頁</a></body></html>'),
        second: _page(second, "<html><body><p>衛教內容。</p></body></html>"),
    }

    def fetcher(url):
        fetched.append(url)
        return pages[url]  # robots.txt 不在字典裡，取不到即視為未設限（既有行為）

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=5, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl(source)

    visited = [url for url in fetched if not url.endswith("robots.txt")]
    assert visited == [source.url, second], "純導覽的種子頁仍要被走過並跟隨其連結"
    assert [page.url for page in result.pages] == [second], "只有真的有內文的頁面才收成文件"
    assert source.url in result.skipped_urls


def _robots(body: str) -> FetchedPage:
    return FetchedPage(
        url="https://www.hpa.gov.tw/robots.txt",
        content_type="text/plain",
        body=body.encode("utf-8"),
        fetched_at=datetime(2026, 8, 1),
    )


def test_crawler_skips_urls_disallowed_by_robots_txt():
    """國健署 robots.txt 明文禁止 /Pages/ashx/GetFile.ashx，爬蟲不得抓取。

    2026-08-01 盤點正式庫時發現 25 筆文件正是從被禁止的路徑抓來的——
    當時 crawler 完全沒有讀 robots.txt。這裡刻意用國健署的原始格式
    （User-agent 後空一行才寫 Disallow），因為 Python 的 RobotFileParser
    遇空行會重置狀態、把規則整組丟掉。
    """
    source = SourceRegistry().get("hpa_health_education")
    blocked = "https://www.hpa.gov.tw/Pages/ashx/GetFile.ashx?nodeid=39&pid=9"
    allowed = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1"
    pages = {
        "https://www.hpa.gov.tw/robots.txt": _robots(
            "User-agent: *\n\nDisallow: /File\nDisallow: /Pages/ashx/GetFile.ashx\n"
        ),
        allowed: _page(allowed, "<html><body>飲食與運動衛教內容</body></html>"),
        blocked: _page(blocked, "<html><body>不該被抓到的附件</body></html>"),
    }
    fetched: list[str] = []

    def fetcher(url: str) -> FetchedPage:
        fetched.append(url)
        return pages[url]

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=10, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl_urls(source, (allowed, blocked))

    assert blocked not in fetched
    assert blocked in result.skipped_urls
    assert allowed in fetched


def test_crawler_proceeds_when_robots_txt_is_unavailable():
    """robots.txt 取不到時放行——這是慣例，也避免站方暫時故障就整批停擺。"""
    source = SourceRegistry().get("hpa_health_education")
    article = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1"
    pages = {article: _page(article, "<html><body>飲食與運動衛教內容</body></html>")}

    def fetcher(url: str) -> FetchedPage:
        if url.endswith("/robots.txt"):
            raise RuntimeError("robots.txt 取不到")
        return pages[url]

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=10, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl_urls(source, (article,))

    assert len(result.pages) == 1
    assert result.failed_urls == ()


def test_robots_txt_is_fetched_once_per_host():
    """robots.txt 每個網域只取一次，不隨每頁重抓。"""
    source = SourceRegistry().get("hpa_health_education")
    first = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1"
    second = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=2"
    pages = {
        "https://www.hpa.gov.tw/robots.txt": _robots("User-agent: *\nDisallow: /File\n"),
        first: _page(first, "<html><body>衛教內容一</body></html>"),
        second: _page(second, "<html><body>衛教內容二</body></html>"),
    }
    fetched: list[str] = []

    def fetcher(url: str) -> FetchedPage:
        fetched.append(url)
        return pages[url]

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=10, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )
    crawler.crawl_urls(source, (first, second))

    assert fetched.count("https://www.hpa.gov.tw/robots.txt") == 1


def test_redirect_into_disallowed_path_is_dropped():
    """轉址落到 robots.txt 禁止的路徑也要擋。

    2026-08-01 對真實網站實測發現的漏洞：hpa 的 Detail.aspx 附件項目會 302 轉到
    GetFile.ashx，而 robots.txt 明文禁止該路徑。只在送出請求前檢查是不夠的——
    正式庫裡那 25 筆違規文件正是這樣進來的，不是從連結爬到的。
    """
    source = SourceRegistry().get("hpa_health_education")
    requested = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=39&pid=1"
    landed = "https://www.hpa.gov.tw/Pages/ashx/GetFile.ashx?sid=abc"
    pages = {
        "https://www.hpa.gov.tw/robots.txt": _robots(
            "User-agent: *\n\nDisallow: /Pages/ashx/GetFile.ashx\n"
        ),
        requested: FetchedPage(
            url=landed,
            content_type="text/html; charset=utf-8",
            body="<html><body>附件內容不該被收錄</body></html>".encode(),
            fetched_at=datetime(2026, 8, 1),
        ),
    }

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=10, delay_seconds=0),
        fetcher=lambda url: pages[url],
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl_urls(source, (requested,))

    assert result.pages == ()
    assert landed in result.skipped_urls


_SITEMAP_XML = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>http://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&amp;pid=3748</loc></url>
  <url><loc>http://www.hpa.gov.tw/Pages/List.aspx?nodeid=39</loc></url>
  <url><loc>https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=46&amp;pid=99#top</loc></url>
  <url><loc>https://evil.example/Pages/Detail.aspx?pid=1</loc></url>
  <url><loc>http://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&amp;pid=3748</loc></url>
</urlset>
"""


def test_load_sitemap_urls_keeps_only_article_pages_of_allowed_domains():
    from kinsun.rag.crawler import load_sitemap_urls

    source = SourceRegistry().get("hpa_health_education")

    urls = load_sitemap_urls(_SITEMAP_XML.encode("utf-8"), source)

    assert urls == (
        # &amp; 還原、http 升級 https、#fragment 去除、跨網域與列表頁剔除、重複去除
        "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=3748",
        "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=46&pid=99",
    )


def test_load_sitemap_urls_without_content_pattern_keeps_every_page():
    from dataclasses import replace

    from kinsun.rag.crawler import load_sitemap_urls

    source = replace(SourceRegistry().get("hpa_health_education"), content_url_pattern="")

    urls = load_sitemap_urls(_SITEMAP_XML.encode("utf-8"), source)

    assert "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=39" in urls
    assert all("evil.example" not in url for url in urls)


def test_load_sitemap_urls_returns_empty_on_malformed_xml():
    from kinsun.rag.crawler import load_sitemap_urls

    source = SourceRegistry().get("hpa_health_education")

    assert load_sitemap_urls(b"<urlset><url><loc>x", source) == ()


def test_crawl_sitemap_fetches_only_listed_articles():
    """sitemap 取代爬樹：清單上有什麼就抓什麼，不跟隨頁內連結。"""
    source = SourceRegistry().get("hpa_health_education")
    article_a = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=3748"
    article_b = "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=46&pid=99"
    pages = {
        source.sitemap_url: FetchedPage(
            url=source.sitemap_url,
            content_type="text/xml",
            body=_SITEMAP_XML.encode("utf-8"),
            fetched_at=datetime(2026, 8, 1),
        ),
        article_a: _page(
            article_a,
            "<html><body>不運動就瘦不下來嗎的衛教內容"
            '<a href="https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=99&pid=1">別的文章</a>'
            "</body></html>",
        ),
        article_b: _page(article_b, "<html><body>慢性病防治衛教內容</body></html>"),
    }
    fetched: list[str] = []

    def fetcher(url: str) -> FetchedPage:
        fetched.append(url)
        return pages[url]

    crawler = HealthEducationCrawler(
        config=CrawlerConfig(max_pages_per_source=100, delay_seconds=0),
        fetcher=fetcher,
        sleeper=lambda seconds: None,
    )

    result = crawler.crawl_sitemap(source)

    assert len(result.pages) == 2
    # 頁內連結完全不跟隨，主題不會漂移
    assert "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=99&pid=1" not in fetched


_RSS_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>衛生福利部疾病管制署</title>
  <link>https://www.cdc.gov.tw/</link>
  <item>
    <title>流感併發重症</title>
    <link>https://www.cdc.gov.tw/Disease/SubIndex/AbCd1234</link>
  </item>
  <item>
    <title>侵襲性肺炎鏈球菌感染症</title>
    <link>http://www.cdc.gov.tw/Disease/SubIndex/EfGh5678</link>
  </item>
  <item>
    <title>某則公告</title>
    <link>https://www.cdc.gov.tw/Bulletin/List/ZzZz0000</link>
  </item>
</channel></rss>
"""


def test_load_sitemap_urls_reads_rss_item_links():
    """疾管署沒有 sitemap，但有 RSS；同一個載入器要能吃兩種格式。

    2026-08-01 實測：cdc 用爬樹只抓到同一個索引頁的 17 種參數變形，內容全是選單。
    RSS 的 type=2 feed 直接列出 97 個疾病頁，那才是真正的內容清單。
    """
    from dataclasses import replace

    from kinsun.rag.crawler import load_sitemap_urls

    source = replace(
        SourceRegistry().get("cdc_diseases"),
        content_url_pattern=r"Disease/SubIndex",
        allowed_domains=("cdc.gov.tw",),
    )

    urls = load_sitemap_urls(_RSS_FEED.encode("utf-8"), source)

    assert urls == (
        "https://www.cdc.gov.tw/Disease/SubIndex/AbCd1234",
        # http 升級 https，與 sitemap 路徑套用同一套正規化
        "https://www.cdc.gov.tw/Disease/SubIndex/EfGh5678",
    )
    # channel 層的首頁連結與不符內容樣式的公告頁都不收
    assert all("Bulletin" not in url for url in urls)


def test_pdf_title_comes_from_the_download_filename():
    """PDF 沒有 <title>，標題取自 Content-Disposition 的檔名。

    2026-08-02 實測國健署 health.hpa.gov.tw 的下載端點：網址是
    `Download.ashx?f=<guid>.pdf&o=<檔名>.pdf`，路徑段只有 "Download"。
    標題會被接在內文前面一起送進嵌入模型（含標題 R@1 98.4%、純內文 85.2%），
    也是引用時顯示給家屬看的字，取成 "Download" 兩邊都毀了。
    伺服器送的 filename 是 percent-encoded UTF-8，需解碼。
    """
    page = FetchedPage(
        url="https://health.hpa.gov.tw/common/Download.ashx?f=abc.pdf&o=x.pdf",
        content_type="application/pdf",
        body=b"%PDF-1.4",
        fetched_at=datetime.now(),
        content_disposition=(
            'attachment; filename="05.%e7%9d%a1%e7%9c%a0%e8%88%87'
            '%e7%b2%be%e7%a5%9e%e5%81%a5%e5%ba%b7.pdf"'
        ),
    )

    assert _pdf_title(page) == "05.睡眠與精神健康"


def test_pdf_title_falls_back_to_the_url_path():
    """沒有 Content-Disposition 時維持既有行為：取網址最後一段。"""
    page = FetchedPage(
        url="https://example.gov.tw/files/%E8%A1%9B%E6%95%99.pdf",
        content_type="application/pdf",
        body=b"%PDF-1.4",
        fetched_at=datetime.now(),
    )

    assert _pdf_title(page) == "衛教"


def test_anchor_text_is_not_kept_as_document_content():
    """連結裡的文字是導覽，不是內文。

    2026-08-07 實測定案：政府網站的選單就是一堆連結，其文字全部包在 <a> 裡——
    國健署每頁 <a> 內恆為 3,084 字（各頁一字不差的全站選單），<a> 外才是文章
    （實測三篇各 894／740／695 字）。先前壓平全頁再用外形猜哪段是選單，失敗過
    五次（長度下限→欄位數→條列比例→跨文件行重複→重複次數門檻），且每次都會
    誤殺簡短的真衛教。改在解析當下就依結構分流，不再事後猜。

    附件與相關文件的標題同理：疾管署〈新冠併發重症〉頁的 <a> 內是〈臨床處置
    指引〉〈疫苗接種須知〉等十餘份**別份文件**的標題，收進來等於把疾病介紹的
    向量污染成一份文件目錄。
    """
    # 選單與附件清單就放在內容區裡面——這是真實情況：疾管署與國健署的側欄選單
    # 和「相關檔案」都渲染在 <main> 之內，不在 <nav> 裡，既有的主內容區規則攔不到。
    html = (
        "<html><body><main>"
        "<a href='/menu-a'>關於本署</a><a href='/menu-b'>大事紀要</a>"
        "<h1>貓抓病</h1>"
        "<p>貓抓病是由韓瑟勒巴通氏菌所引起的疾病，主要流行季節在夏末及秋冬。</p>"
        "<p>患者常因先前遭受貓抓、舔或咬傷而發病。</p>"
        "<a href='/file-1'>新型冠狀病毒感染臨床處置指引</a>"
        "</main></body></html>"
    )
    parser = HtmlTextExtractor("https://www.cdc.gov.tw/Disease/SubIndex/x")
    parser.feed(html)

    assert "韓瑟勒巴通氏菌" in parser.text
    assert "關於本署" not in parser.text
    assert "大事紀要" not in parser.text
    assert "臨床處置指引" not in parser.text


def test_dropping_anchor_text_does_not_stop_link_discovery():
    """⚠️ 不收連結文字，但連結本身照收——爬蟲整條路靠它，斷了就什麼都抓不到。"""
    html = (
        "<html><body><article>"
        "<a href='/Pages/Detail.aspx?pid=1'>第一篇</a>"
        "<p>正文。</p>"
        "<a href='https://www.hpa.gov.tw/Pages/Detail.aspx?pid=2'>第二篇</a>"
        "</article></body></html>"
    )
    parser = HtmlTextExtractor("https://www.hpa.gov.tw/Pages/List.aspx")
    parser.feed(html)

    assert parser.links == (
        "https://www.hpa.gov.tw/Pages/Detail.aspx?pid=1",
        "https://www.hpa.gov.tw/Pages/Detail.aspx?pid=2",
    )
    assert "第一篇" not in parser.text
