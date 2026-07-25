"""新聞來源抓取器介面：每個新聞來源實作一個 fetcher，回傳 NewsItem 清單。

新增新聞來源＝新寫一個實作此介面的 fetcher，不需要改動 NewsStore 或 jobs.py。
"""

from __future__ import annotations

from typing import Protocol

from kinsun.news.models import NewsItem


class NewsFetcher(Protocol):
    def fetch(self) -> list[NewsItem]: ...
