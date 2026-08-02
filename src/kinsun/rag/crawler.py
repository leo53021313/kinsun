"""衛教 RAG 大型 crawler 核心。

以標準庫實作，讓 Windows／macOS／DGX 都能跑；PDF 文字抽取採可選 pypdf。
"""

from __future__ import annotations

import http.cookiejar
import json
import logging
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser

from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

from kinsun.rag.schemas import Source
from kinsun.rag.text_cleaner import clean_text

logger = logging.getLogger("kinsun.rag.crawler")

_INLINE_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
# 只跳過表單「控制元件」而非 <form> 容器：ASP.NET WebForms（如 hpa.gov.tw）
# 會把整頁內容包在單一 <form> 內，跳過容器等於丟掉全部內文。
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "nav",
    "footer",
    "header",
    "aside",
    "button",
    "select",
    "option",
    "textarea",
    "label",
    "datalist",
}
_PRIMARY_TAGS = {"main", "article"}


@dataclass(frozen=True)
class CrawlerConfig:
    max_pages_per_source: int = 80
    delay_seconds: float = 0.5
    timeout_seconds: float = 20.0
    retries: int = 2
    user_agent: str = "KinSun-RAG-Crawler/1.0 (education demo; contact: classroom project)"


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: str
    body: bytes
    fetched_at: datetime


@dataclass(frozen=True)
class ParsedPage:
    url: str
    title: str
    text: str
    links: tuple[str, ...]
    published_at: date | None
    parser_used: str


@dataclass(frozen=True)
class CrawlResult:
    source_id: str
    pages: tuple[ParsedPage, ...]
    skipped_urls: tuple[str, ...]
    failed_urls: tuple[tuple[str, str], ...]


class HtmlTextExtractor(HTMLParser):
    def __init__(self, base_url: str, content_pattern: re.Pattern[str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._content_pattern = content_pattern
        self._skip_depth = 0
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._primary_depth = 0
        self._primary_parts: list[str] = []
        self._fallback_parts: list[str] = []
        self._links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag in _PRIMARY_TAGS:
            self._primary_depth += 1
        # 導覽／頁尾的連結一律不收，符合內容樣式者也不例外。
        # ⚠️ 2026-08-01 實測推翻了先前的判讀：hpa 列表頁 37 個 Detail 連結有 29 個
        # 位於 nav／header／footer，當時誤判為「文章住在導覽區」而網開一面，結果
        # 兩個不同主題的來源抓回一模一樣的 19 篇——本署簡介、組織架構圖、各業務
        # 服務窗口、本署位置……那 29 個是每頁都有的機關樣板頁，只是網址型態剛好
        # 也像文章。真正的主題文章是內容區那幾個。
        if tag == "a" and self._skip_depth == 0:
            href = dict(attrs).get("href")
            if href:
                self._links.append(urllib.parse.urljoin(self._base_url, href))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in _PRIMARY_TAGS and self._primary_depth:
            self._primary_depth -= 1

    def handle_data(self, data: str) -> None:
        cleaned = _clean_inline(data)
        if not cleaned:
            return
        if self._title_depth:
            self._title_parts.append(cleaned)
        if self._skip_depth == 0:
            self._fallback_parts.append(cleaned)
            if self._primary_depth:
                self._primary_parts.append(cleaned)

    @property
    def title(self) -> str:
        return _clean_inline(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        parts = self._primary_parts or self._fallback_parts
        return clean_text("\n".join(parts))

    @property
    def links(self) -> tuple[str, ...]:
        # 跳脫 href（\"…\"）經 urljoin 會變成含引號／反斜線的垃圾 URL，直接剔除。
        return tuple(
            dict.fromkeys(
                _strip_fragment(link)
                for link in self._links
                if "\\" not in link and '"' not in link
            )
        )


class DomainParserRegistry:
    """依網域選 parser；目前 domain parser 共用清洗器，但保留擴充點。"""

    def parse(self, page: FetchedPage, source: Source) -> ParsedPage:
        if _is_pdf(page):
            return self._parse_pdf(page, source)
        content_type = page.content_type.lower()
        if "json" in content_type or page.url.lower().endswith(".json"):
            return self._parse_json(page, source)
        # 內容嗅探：hpa newsapi.ashx 等端點回 JSON 但 Content-Type 標 text/html，
        # 誤走 HTML parser 會把跳脫 href 撿成垃圾連結。
        if page.body.lstrip()[:1] in (b"{", b"["):
            try:
                return self._parse_json(page, source)
            except json.JSONDecodeError:
                pass
        if "xml" in content_type or "rss" in content_type or page.url.lower().endswith(".xml"):
            return self._parse_xml(page, source)
        if content_type.startswith("image/"):
            return ParsedPage(page.url, source.title, "", (), None, "image:skipped")
        return self._parse_html(page, source)

    def _parse_html(self, page: FetchedPage, source: Source) -> ParsedPage:
        html = page.body.decode(_guess_charset(page.content_type), errors="ignore")
        parser = HtmlTextExtractor(page.url, _content_pattern(source))
        parser.feed(html)
        title = parser.title or source.title
        text = parser.text
        return ParsedPage(
            url=page.url,
            title=title,
            text=text,
            links=parser.links,
            published_at=_infer_date(f"{title}\n{text}"),
            parser_used=f"html:{_domain(page.url)}",
        )

    def _parse_pdf(self, page: FetchedPage, source: Source) -> ParsedPage:
        text = _extract_pdf_text(page.body)
        return ParsedPage(
            url=page.url,
            title=_pdf_title(page.url) or source.title,
            text=text,
            links=(),
            published_at=_infer_date(text),
            parser_used="pdf:pypdf",
        )

    def _parse_json(self, page: FetchedPage, source: Source) -> ParsedPage:
        payload = json.loads(page.body.decode(_guess_charset(page.content_type), errors="ignore"))
        text_parts: list[str] = []
        links: list[str] = []
        _collect_json(payload, text_parts=text_parts, links=links)
        text = clean_text("\n".join(text_parts))
        return ParsedPage(
            url=page.url,
            title=source.title,
            text=text,
            links=tuple(dict.fromkeys(_strip_fragment(link) for link in links)),
            published_at=_infer_date(text),
            parser_used=f"json:{_domain(page.url)}",
        )

    def _parse_xml(self, page: FetchedPage, source: Source) -> ParsedPage:
        root = ET.fromstring(page.body)
        text_parts = [text.strip() for text in root.itertext() if text and text.strip()]
        links: list[str] = []
        for node in root.iter():
            href = node.attrib.get("href")
            if href:
                links.append(urllib.parse.urljoin(page.url, href))
            if node.tag.rsplit("}", 1)[-1].lower() == "link" and node.text:
                candidate = node.text.strip()
                if candidate.startswith(("http://", "https://")):
                    links.append(candidate)
        text = clean_text("\n".join(text_parts))
        return ParsedPage(
            url=page.url,
            title=source.title,
            text=text,
            links=tuple(dict.fromkeys(_strip_fragment(link) for link in links)),
            published_at=_infer_date(text),
            parser_used=f"xml:{_domain(page.url)}",
        )


class HealthEducationCrawler:
    def __init__(
        self,
        *,
        config: CrawlerConfig | None = None,
        parser: DomainParserRegistry | None = None,
        fetcher=None,
        sleeper=time.sleep,
    ) -> None:
        self._config = config or CrawlerConfig()
        self._parser = parser or DomainParserRegistry()
        self._fetcher = fetcher or self._fetch
        self._sleep = sleeper
        # 每個 crawler 一份 cookie jar：health99 等站台先發 session cookie 再轉址回
        # 同一網址，不收 cookie 會被 urllib 判定為無限轉址（2026-07-28 實測 84/85 頁全滅）。
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        # 每個 origin 一份 robots 規則，取不到時存 None 代表放行，避免每頁重抓。
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _is_allowed_by_robots(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        rules = self._robots[origin]
        return True if rules is None else rules.can_fetch(self._config.user_agent, url)

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            fetched = self._fetcher(f"{origin}/robots.txt")
        except Exception as exc:  # noqa: BLE001 - 取不到 robots.txt 時放行（業界慣例）
            logger.info("RAG 取不到 %s/robots.txt，本次不套用限制：%s", origin, exc)
            return None
        body = fetched.body.decode("utf-8", errors="replace")
        parser = urllib.robotparser.RobotFileParser()
        # 先濾掉空行再交給 stdlib：RFC 9309 的群組由 user-agent 行分隔，空行不終止群組，
        # 但 Python 的 RobotFileParser 一遇空行就重置狀態，會把後續 Disallow 整組丟掉。
        # hpa.gov.tw 的 robots.txt 正是「User-agent: *」後空一行才寫 Disallow
        # （2026-08-01 實測：不濾空行時 can_fetch(GetFile.ashx) 回 True，等於形同無限制）。
        parser.parse([line for line in body.splitlines() if line.strip()])
        return parser

    def crawl(self, source: Source) -> CrawlResult:
        # 兩條佇列：文章頁優先於其他頁。max_pages 有限時，先把預算花在內容上
        # （2026-07-30 實測純 BFS 爬 885 頁只換到 58 篇文章，其餘是導覽與列表頁）。
        pattern = _content_pattern(source)
        content_queue: deque[str] = deque()
        queue = deque([source.url])
        seen: set[str] = set()
        pages: list[ParsedPage] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []

        while (content_queue or queue) and len(seen) < self._config.max_pages_per_source:
            pending = content_queue or queue
            url = _upgrade_to_https(_strip_fragment(pending.popleft()))
            if url in seen:
                continue
            seen.add(url)
            if not _is_allowed_url(url, source.allowed_domains):
                skipped.append(url)
                continue
            if not self._is_allowed_by_robots(url):
                skipped.append(url)
                continue
            try:
                fetched = self._fetcher(url)
                if not self._is_allowed_by_robots(fetched.url):
                    skipped.append(fetched.url)
                    continue
                parsed = self._parser.parse(fetched, source)
                if parsed.text.strip():
                    pages.append(parsed)
                else:
                    skipped.append(url)
                budget = self._config.max_pages_per_source
                # 宣告了內容樣式的來源：文章是葉節點，不從文章再往外爬。
                # 2026-08-01 實測——只做「文章優先」時，爬蟲會從文章跳到文章，
                # 一路漂到菸害防制英文新聞稿與業務服務窗口（前 14 篇有 10 篇是英文），
                # 主題完全不是長輩衛教。列表頁本身就是機關做好的策展，守住它即可。
                is_leaf = pattern is not None and pattern.search(url)
                for link in () if is_leaf else parsed.links:
                    if not _is_allowed_url(link, source.allowed_domains) or link in seen:
                        continue
                    if pattern is not None and pattern.search(link):
                        # 文章連結一律收（只受總量上限節制）：預算檢查若一視同仁，
                        # 排在其他連結後面的文章會永遠擠不進待爬清單。
                        if len(content_queue) < budget:
                            content_queue.append(link)
                    elif len(seen) + len(queue) + len(content_queue) < budget:
                        # 列表頁照跟：文章多半掛在子分類底下（2026-08-01 實測：
                        # 慢性病防治列表頁的內容區有 43 個子分類、只有 7 篇文章
                        # 直掛，只收直掛的話每個來源僅剩 6 篇）。
                        # ⚠️ 主題會飄——hpa 的左側全站分類選單是普通 <div> 而非
                        # <nav>，擋不掉，故子分類會通往兄弟分類。深度限制試過，
                        # 對結果毫無影響（飄題從種子頁就開始），已移除。
                        # Leo 2026-08-01 核定：全部收進來、不過濾行政公告。
                        queue.append(link)
                self._sleep(self._config.delay_seconds)
            except Exception as exc:  # noqa: BLE001 - 單頁失敗不可中斷整批
                logger.warning("RAG crawler 讀取失敗：%s (%s)", url, exc)
                failed.append((url, str(exc)))
        return CrawlResult(
            source_id=source.source_id,
            pages=tuple(pages),
            skipped_urls=tuple(skipped),
            failed_urls=tuple(failed),
        )

    def crawl_sitemap(self, source: Source) -> CrawlResult:
        """讀 sitemap 取得文章清單後只抓清單上的網址，完全不跟隨頁內連結。

        取代 `crawl()` 的爬樹路徑。爬樹在每頁都渲染全站選單的網站上必然漂移，
        sitemap 則是站方自己宣告的內容清單，沒有猜測空間。
        """
        fetched = self._fetcher(source.sitemap_url)
        urls = load_sitemap_urls(fetched.body, source)
        logger.info("RAG 來源 %s 的 sitemap 取得 %d 個文章網址", source.source_id, len(urls))
        return self.crawl_urls(source, urls)

    def crawl_urls(self, source: Source, urls: tuple[str, ...]) -> CrawlResult:
        """只更新已知 URL，不跟隨連結；新連結留給 discovery 稽核。"""
        pages: list[ParsedPage] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []
        for raw_url in dict.fromkeys(urls):
            url = _upgrade_to_https(_strip_fragment(raw_url))
            if not _is_allowed_url(url, source.allowed_domains):
                skipped.append(url)
                continue
            if not self._is_allowed_by_robots(url):
                skipped.append(url)
                continue
            try:
                fetched = self._fetcher(url)
                # 轉址後的落點要重驗：hpa 的 Detail.aspx 附件項目會 302 到
                # robots.txt 禁止的 GetFile.ashx，只在送出前檢查會整批漏掉。
                if not self._is_allowed_by_robots(fetched.url):
                    skipped.append(fetched.url)
                    continue
                parsed = self._parser.parse(fetched, source)
                if parsed.text.strip():
                    pages.append(parsed)
                else:
                    skipped.append(url)
                self._sleep(self._config.delay_seconds)
            except Exception as exc:  # noqa: BLE001 - 單頁失敗不影響其他 URL
                logger.warning("RAG 已知 URL 更新失敗：%s (%s)", url, exc)
                failed.append((url, str(exc)))
        return CrawlResult(source.source_id, tuple(pages), tuple(skipped), tuple(failed))

    def _fetch(self, url: str) -> FetchedPage:
        def _once() -> FetchedPage:
            request = urllib.request.Request(
                _encode_request_url(url),
                headers={"User-Agent": self._config.user_agent},
                method="GET",
            )
            with self._opener.open(  # noqa: S310 - URL 已由 source allowlist 限制
                request,
                timeout=self._config.timeout_seconds,
            ) as response:
                return FetchedPage(
                    url=response.geturl(),
                    content_type=response.headers.get("Content-Type", ""),
                    body=response.read(),
                    fetched_at=datetime.now(),
                )

        # 固定間隔重試 retries+1 次；重試間睡 delay_seconds（走注入的 self._sleep 供測試斷言）。
        # 耗盡後把最後一個錯誤統一翻成 RuntimeError，維持單頁失敗不中斷整批的既有語意。
        try:
            return Retrying(
                stop=stop_after_attempt(self._config.retries + 1),
                wait=wait_fixed(self._config.delay_seconds),
                sleep=self._sleep,
                reraise=False,
            )(_once)
        except RetryError as exc:
            raise RuntimeError(exc.last_attempt.exception() or "fetch failed") from exc


def load_sitemap_urls(body: bytes, source: Source) -> tuple[str, ...]:
    """從內容清單（sitemap.xml 或 RSS）取出屬於本來源的文章網址。

    兩種格式都吃：sitemap 用 `<loc>`、RSS 用 `<item><link>`。cdc.gov.tw 沒有
    sitemap 但有 RSS，兩者在管線裡扮演同一個角色——站方自己宣告的內容清單。

    只留下 `content_url_pattern` 命中的網址（留空則全收）與 allowlist 內的網域，
    並套用與爬取路徑相同的正規化（http→https、去 fragment），確保去重一致。
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("RAG 來源 %s 的 sitemap 解析失敗：%s", source.source_id, exc)
        return ()

    pattern = _content_pattern(source)
    urls: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in ("loc", "link") or not node.text:
            continue
        url = _upgrade_to_https(_strip_fragment(unescape(node.text.strip())))
        if not _is_allowed_url(url, source.allowed_domains):
            continue
        if pattern is not None and not pattern.search(url):
            continue
        urls.append(url)
    return tuple(dict.fromkeys(urls))


def _content_pattern(source: Source) -> re.Pattern[str] | None:
    if not source.content_url_pattern:
        return None
    try:
        return re.compile(source.content_url_pattern)
    except re.error as exc:
        logger.warning("RAG 來源 %s 的 content_url_pattern 無效：%s", source.source_id, exc)
        return None


def _clean_inline(text: str) -> str:
    return _INLINE_SPACE_RE.sub(" ", unescape(text)).strip()


def _strip_fragment(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _upgrade_to_https(url: str) -> str:
    """站內舊 http:// 連結一律升級 https（政府網站對 http 常直接 403，實測無 http 成功案例）。"""
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def _encode_request_url(url: str) -> str:
    """URL 含非 ASCII（如中文附件檔名）時 percent-encode；safe 含 % 避免重複編碼既有 %XX。"""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            urllib.parse.quote(parsed.path, safe="/%"),
            urllib.parse.quote(parsed.query, safe="=&%+"),
            "",
        )
    )


def _domain(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


def _is_allowed_url(url: str, allowed_domains: tuple[str, ...]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _guess_charset(content_type: str) -> str:
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value
    return "utf-8"


def _is_pdf(page: FetchedPage) -> bool:
    return "application/pdf" in page.content_type.lower() or page.url.lower().endswith(".pdf")


def _extract_pdf_text(body: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # noqa: BLE001 - 可選依賴
        raise RuntimeError("讀取 PDF 需要安裝 pypdf；請先處理 HTML 來源或安裝 pypdf。") from exc

    from io import BytesIO

    reader = PdfReader(BytesIO(body))
    return clean_text("\n".join(page.extract_text() or "" for page in reader.pages))


def _pdf_title(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
    return name.rsplit(".", 1)[0]


def _infer_date(text: str) -> date | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _collect_json(value, *, text_parts: list[str], links: list[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_json(item, text_parts=text_parts, links=links)
        return
    if isinstance(value, list):
        for item in value:
            _collect_json(item, text_parts=text_parts, links=links)
        return
    if not isinstance(value, str):
        return
    stripped = value.strip()
    if not stripped:
        return
    if stripped.startswith(("http://", "https://")):
        links.append(stripped)
    else:
        text_parts.append(stripped)
