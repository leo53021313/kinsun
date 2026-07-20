"""衛福部新聞列表爬蟲：免金鑰，重用 rag/crawler.py 的 HtmlTextExtractor 解析內文頁。

列表頁結構為衛福部網站特有（<li><a href title><p>標題</p><time>民國日期</time></a></li>），
故列表頁另寫小型 HTMLParser；內文頁的純文字抽取則直接重用既有的 HtmlTextExtractor，
不重新發明一套 HTML 解析。
"""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser

from kinsun.news.fetchers._ids import make_news_item_id
from kinsun.news.models import NewsItem
from kinsun.rag.crawler import HtmlTextExtractor
from kinsun.transport import HttpxTransport, Transport, TransportError

logger = logging.getLogger("kinsun.news.mohw")

_USER_AGENT = "KinSun-News-Fetcher/1.0 (education demo; contact: classroom project)"
_LIST_URL = "https://www.mohw.gov.tw/lp-16-1.html"
_LIST_URL_PAGE = "https://www.mohw.gov.tw/lp-16-1-{page}-20.html"
_PUBLISHER = "衛生福利部"
SOURCE_ID = "mohw"


class _MohwListParser(HTMLParser):
    """解析衛福部新聞列表頁，抽出每則新聞的標題、連結與（民國）發布日期。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str, str]] = []  # (title, href, roc_date_text)
        self._href = ""
        self._title = ""
        self._in_anchor = False
        self._in_time = False
        self._date_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("href"):
            self._in_anchor = True
            self._href = attrs_dict.get("href") or ""
            self._title = attrs_dict.get("title") or ""
            self._date_parts = []
        elif tag == "time" and self._in_anchor:
            self._in_time = True

    def handle_data(self, data: str) -> None:
        if self._in_time:
            self._date_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "time":
            self._in_time = False
        elif tag == "a" and self._in_anchor:
            date_text = "".join(self._date_parts).strip()
            if self._href and date_text:
                self.entries.append((self._title, self._href, date_text))
            self._in_anchor = False


def _parse_roc_date(date_text: str) -> float | None:
    """民國日期（如 "115-07-20"）轉 epoch 秒；格式不符回 None（不擋整批抓取）。"""
    parts = date_text.strip().split("-")
    if len(parts) != 3:
        return None
    try:
        roc_year, month, day = (int(p) for p in parts)
        return datetime(roc_year + 1911, month, day, tzinfo=UTC).timestamp()
    except ValueError:
        return None


class MohwNewsFetcher:
    """衛福部新聞列表＋內文爬蟲（NewsFetcher 實作，免金鑰）。"""

    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        transport: Transport | None = None,
        max_pages: int = 1,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._clock = clock
        self._transport = transport or HttpxTransport()
        self._max_pages = max_pages
        self._timeout = timeout_seconds

    def fetch(self) -> list[NewsItem]:
        now = self._clock().timestamp()
        items: list[NewsItem] = []
        for page in range(1, self._max_pages + 1):
            list_url = _LIST_URL if page == 1 else _LIST_URL_PAGE.format(page=page)
            html = self._get(list_url)
            if html is None:
                continue
            parser = _MohwListParser()
            parser.feed(html)
            if not parser.entries:
                break
            for title, href, date_text in parser.entries:
                url = href if href.startswith("http") else urllib.parse.urljoin(list_url, href)
                items.append(
                    NewsItem(
                        news_item_id=make_news_item_id(SOURCE_ID, url),
                        source_id=SOURCE_ID,
                        title=title,
                        url=url,
                        publisher=_PUBLISHER,
                        content=self._fetch_content(url) or title,
                        published_at=_parse_roc_date(date_text),
                        retrieved_at=now,
                    )
                )
        return items

    def _get(self, url: str) -> str | None:
        try:
            response = self._transport.request(
                "GET", url, headers={"User-Agent": _USER_AGENT}, timeout=self._timeout
            )
        except TransportError:
            logger.warning("衛福部新聞頁面抓取失敗：%s", url)
            return None
        if response.status != 200:
            logger.warning("衛福部新聞頁面回應非 200：%s status=%s", url, response.status)
            return None
        return response.body.decode("utf-8", errors="ignore")

    def _fetch_content(self, url: str) -> str:
        html = self._get(url)
        if html is None:
            return ""
        extractor = HtmlTextExtractor(url)
        extractor.feed(html)
        return extractor.text
