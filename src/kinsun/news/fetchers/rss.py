"""通用 RSS 2.0 新聞抓取器（NewsFetcher 實作，免金鑰）。

News API 的索引沒收台灣本土媒體（07 v1.20 診斷），RSS 是從根本補洞的路：
台媒與 Google News 台灣版都有免費公開 feed。一個 fetcher 吃一條 feed 網址，
feed 清單走 `NEWS_RSS_FEEDS`（composition／worker 端逐條建實例）。

Google News 慣例的兩個小處理：每則的 <source> 才是實際媒體名（頻道名是
「Google 新聞」）；標題帶「 - 媒體名」尾綴，去掉避免重複念。
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import StringIO

from kinsun.news.fetchers._ids import make_news_item_id
from kinsun.news.models import NewsItem
from kinsun.transport import HttpxTransport, Transport, TransportError

logger = logging.getLogger("kinsun.news.rss")

_USER_AGENT = "KinSun-News-Fetcher/1.0 (education demo; contact: classroom project)"
SOURCE_ID = "rss"


class _TextOnly(HTMLParser):
    """把 description 內的 HTML 剝成純文字（RSS 摘要常夾連結標籤）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf = StringIO()

    def handle_data(self, data: str) -> None:
        self._buf.write(data)

    @property
    def text(self) -> str:
        return self._buf.getvalue().strip()


def _strip_html(raw: str) -> str:
    parser = _TextOnly()
    parser.feed(raw)
    return parser.text


def _parse_pubdate(raw: str) -> float | None:
    """RFC 822 日期（RSS 慣例）轉 epoch 秒；格式不符回 None（不擋整批）。"""
    if not raw.strip():
        return None
    try:
        return parsedate_to_datetime(raw.strip()).timestamp()
    except (TypeError, ValueError):
        return None


class RssNewsFetcher:
    """單一 RSS feed 的抓取器；多條 feed＝多個實例（組裝端逐條建）。"""

    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        feed_url: str,
        clock: Callable[[], datetime],
        transport: Transport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._feed_url = feed_url
        self._clock = clock
        self._transport = transport or HttpxTransport()
        self._timeout = timeout_seconds

    def fetch(self) -> list[NewsItem]:
        now = self._clock().timestamp()
        try:
            response = self._transport.request(
                "GET", self._feed_url, headers={"User-Agent": _USER_AGENT}, timeout=self._timeout
            )
        except TransportError:
            logger.warning("RSS feed 抓取失敗：%s", self._feed_url)
            return []
        if response.status != 200:
            logger.warning("RSS feed 回應非 200：%s status=%s", self._feed_url, response.status)
            return []
        try:
            root = ET.fromstring(response.body)
        except ET.ParseError:
            logger.warning("RSS feed 非合法 XML：%s", self._feed_url)
            return []

        channel_title = (root.findtext("./channel/title") or "").strip()
        items: list[NewsItem] = []
        for node in root.findall(".//item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            if not title or not link:
                continue
            source_name = (node.findtext("source") or "").strip()
            publisher = source_name or channel_title
            # Google News 標題尾綴「 - 媒體名」：資訊已在 publisher，去掉避免重複念。
            if source_name and title.endswith(f" - {source_name}"):
                title = title[: -len(f" - {source_name}")].strip()
            description = _strip_html(node.findtext("description") or "")
            items.append(
                NewsItem(
                    news_item_id=make_news_item_id(SOURCE_ID, link),
                    source_id=SOURCE_ID,
                    title=title,
                    url=link,
                    publisher=publisher,
                    content=description or title,
                    published_at=_parse_pubdate(node.findtext("pubDate") or ""),
                    retrieved_at=now,
                )
            )
        return items
