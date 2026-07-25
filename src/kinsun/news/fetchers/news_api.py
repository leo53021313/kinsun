"""News API（newsapi.org）新聞抓取，需要 NEWS_API_KEY。"""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable
from datetime import datetime

from kinsun.news.fetchers._ids import make_news_item_id
from kinsun.news.models import NewsItem
from kinsun.transport import HttpxTransport, Transport, TransportError, get_json

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
        domains: str = "",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._clock = clock
        self._transport = transport or HttpxTransport()
        self._query = query
        self._language = language
        # 來源白名單（逗號分隔網域）＝**抓回後按文章網址過濾**，不送給 API——
        # 實測 News API 的 domains 參數只認基底網域（yahoo.com 全球一鍋），台灣本土
        # 媒體（udn／cna／ettoday…）完全沒收錄，伺服器端無法只挑台灣版；排除大陸
        # 來源仍用白名單而非黑名單（zh 不分繁簡、黑名單抓不完）。條目比對＝完全
        # 相符或其子網域；留空＝不過濾。
        self._allowed_hosts = [d.strip() for d in domains.split(",") if d.strip()]
        self._timeout = timeout_seconds

    def _host_allowed(self, article_url: str) -> bool:
        if not self._allowed_hosts:
            return True
        host = urllib.parse.urlparse(article_url).netloc
        return any(host == entry or host.endswith("." + entry) for entry in self._allowed_hosts)

    def fetch(self) -> list[NewsItem]:
        now = self._clock().timestamp()
        params = {
            "q": self._query,
            "language": self._language,
            # relevancy 而非 publishedAt：最新優先會被高頻科技站洗版（實測前 100 則
            # 0 台灣 Yahoo；relevancy 18/100）；新舊排序交給 get_news 端做。
            "sortBy": "relevancy",
        }
        url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
        try:
            # 金鑰走 X-Api-Key header 不放 URL：TransportError 訊息與 log 都會帶完整
            # URL，query string 藏金鑰等於多一個外洩面（D-74 後續③）。
            data = get_json(
                self._transport, url, timeout=self._timeout, headers={"X-Api-Key": self._api_key}
            )
        except TransportError:
            logger.warning("News API 查詢失敗：query=%s", self._query)
            return []
        items: list[NewsItem] = []
        for article in data.get("articles", []):
            article_url = article.get("url") or ""
            if not article_url or not self._host_allowed(article_url):
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
