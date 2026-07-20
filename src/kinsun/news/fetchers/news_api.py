"""News API（newsapi.org）新聞抓取，需要 NEWS_API_KEY。"""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable
from datetime import datetime

from kinsun.news.fetchers._ids import make_news_item_id
from kinsun.news.models import NewsItem
from kinsun.transport import Transport, TransportError, UrllibTransport, get_json

logger = logging.getLogger("kinsun.news.news_api")

_ENDPOINT = "https://newsapi.org/v2/everything"
SOURCE_ID = "news_api"


def _parse_published_at(raw: str) -> float | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class NewsApiFetcher:
    """News API `/v2/everything` 端點（NewsFetcher 實作，需要金鑰）。"""

    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        api_key: str,
        clock: Callable[[], datetime],
        transport: Transport | None = None,
        query: str = "台灣",
        language: str = "zh",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._clock = clock
        self._transport = transport or UrllibTransport()
        self._query = query
        self._language = language
        self._timeout = timeout_seconds

    def fetch(self) -> list[NewsItem]:
        now = self._clock().timestamp()
        params = {
            "q": self._query,
            "language": self._language,
            "apiKey": self._api_key,
            "sortBy": "publishedAt",
        }
        url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
        try:
            data = get_json(self._transport, url, timeout=self._timeout)
        except TransportError:
            logger.warning("News API 查詢失敗：query=%s", self._query)
            return []
        items: list[NewsItem] = []
        for article in data.get("articles", []):
            article_url = article.get("url") or ""
            if not article_url:
                continue
            items.append(
                NewsItem(
                    news_item_id=make_news_item_id(SOURCE_ID, article_url),
                    source_id=SOURCE_ID,
                    title=article.get("title") or "",
                    url=article_url,
                    publisher=(article.get("source") or {}).get("name") or "",
                    content=article.get("description") or "",
                    published_at=_parse_published_at(article.get("publishedAt") or ""),
                    retrieved_at=now,
                )
            )
        return items
