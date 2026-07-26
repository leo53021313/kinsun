"""話題新聞的排程 job：每日爬取與過期清除。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from kinsun.cron.scheduler import Job
from kinsun.news.fetchers.protocol import NewsFetcher
from kinsun.news.store import NewsStore

logger = logging.getLogger("kinsun.news")


def build_news_crawl_job(
    *,
    fetchers: list[NewsFetcher],
    store: NewsStore,
    hour: int,
    minute: int = 0,
    name: str = "news-crawl",
) -> Job:
    def run() -> None:
        for fetcher in fetchers:
            try:
                items = fetcher.fetch()
            except Exception:  # noqa: BLE001 - 單一來源失敗不可擋住其他來源
                logger.warning("新聞來源抓取失敗 source=%s", getattr(fetcher, "source_id", "?"))
                continue
            for item in items:
                store.save(item)

    return Job(name=name, cron=f"{minute} {hour} * * *", run=run)


def build_news_cleanup_job(
    *,
    purge: Callable[[], None],
    hour: int,
    minute: int = 45,
    name: str = "news-cleanup",
) -> Job:
    return Job(name=name, cron=f"{minute} {hour} * * *", run=purge)
