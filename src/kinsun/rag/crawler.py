"""衛教 RAG 大型 crawler 核心。

以標準庫實作，讓 Windows／macOS／DGX 都能跑；PDF 文字抽取採可選 pypdf。
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
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
    "form",
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
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
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
        if tag == "a":
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
        return tuple(dict.fromkeys(_strip_fragment(link) for link in self._links))


class DomainParserRegistry:
    """依網域選 parser；目前 domain parser 共用清洗器，但保留擴充點。"""

    def parse(self, page: FetchedPage, source: Source) -> ParsedPage:
        if _is_pdf(page):
            return self._parse_pdf(page, source)
        content_type = page.content_type.lower()
        if "json" in content_type or page.url.lower().endswith(".json"):
            return self._parse_json(page, source)
        if "xml" in content_type or "rss" in content_type or page.url.lower().endswith(".xml"):
            return self._parse_xml(page, source)
        if content_type.startswith("image/"):
            return ParsedPage(page.url, source.title, "", (), None, "image:skipped")
        return self._parse_html(page, source)

    def _parse_html(self, page: FetchedPage, source: Source) -> ParsedPage:
        html = page.body.decode(_guess_charset(page.content_type), errors="ignore")
        parser = HtmlTextExtractor(page.url)
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

    def crawl(self, source: Source) -> CrawlResult:
        queue = deque([source.url])
        seen: set[str] = set()
        pages: list[ParsedPage] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []

        while queue and len(seen) < self._config.max_pages_per_source:
            url = _strip_fragment(queue.popleft())
            if url in seen:
                continue
            seen.add(url)
            if not _is_allowed_url(url, source.allowed_domains):
                skipped.append(url)
                continue
            try:
                fetched = self._fetcher(url)
                parsed = self._parser.parse(fetched, source)
                if parsed.text.strip():
                    pages.append(parsed)
                else:
                    skipped.append(url)
                for link in parsed.links:
                    if len(seen) + len(queue) >= self._config.max_pages_per_source:
                        break
                    if _is_allowed_url(link, source.allowed_domains) and link not in seen:
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

    def crawl_urls(self, source: Source, urls: tuple[str, ...]) -> CrawlResult:
        """只更新已知 URL，不跟隨連結；新連結留給 discovery 稽核。"""
        pages: list[ParsedPage] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []
        for raw_url in dict.fromkeys(urls):
            url = _strip_fragment(raw_url)
            if not _is_allowed_url(url, source.allowed_domains):
                skipped.append(url)
                continue
            try:
                parsed = self._parser.parse(self._fetcher(url), source)
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
                url,
                headers={"User-Agent": self._config.user_agent},
                method="GET",
            )
            with urllib.request.urlopen(  # noqa: S310 - URL 已由 source allowlist 限制
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


def _clean_inline(text: str) -> str:
    return _INLINE_SPACE_RE.sub(" ", unescape(text)).strip()


def _strip_fragment(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


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
