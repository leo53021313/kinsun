from __future__ import annotations

from kinsun.news.jobs import build_news_cleanup_job, build_news_crawl_job
from kinsun.news.models import NewsItem
from kinsun.news.store import FakeNewsStore


def _item(news_item_id: str) -> NewsItem:
    return NewsItem(
        news_item_id=news_item_id,
        source_id="mohw",
        title="標題",
        url=f"https://example.com/{news_item_id}",
        publisher="衛生福利部",
        content="內文",
        published_at=0.0,
        retrieved_at=0.0,
    )


class _Fetcher:
    def __init__(self, items: list[NewsItem], *, source_id: str = "mohw") -> None:
        self._items = items
        self.source_id = source_id

    def fetch(self) -> list[NewsItem]:
        return self._items


class _ExplodingFetcher:
    source_id = "broken"

    def fetch(self) -> list[NewsItem]:
        raise RuntimeError("boom")


def test_crawl_job_saves_items_from_every_fetcher():
    store = FakeNewsStore()
    job = build_news_crawl_job(
        fetchers=[_Fetcher([_item("a1")]), _Fetcher([_item("a2")], source_id="news_api")],
        store=store,
        hour=0,
    )
    job.run()
    saved = {i.news_item_id for i in store.list_recent(since=-1.0)}
    assert saved == {"a1", "a2"}


def test_crawl_job_isolates_a_failing_source():
    store = FakeNewsStore()
    job = build_news_crawl_job(
        fetchers=[_ExplodingFetcher(), _Fetcher([_item("a1")])],
        store=store,
        hour=0,
    )
    job.run()  # 不應拋出
    assert {i.news_item_id for i in store.list_recent(since=-1.0)} == {"a1"}


def test_crawl_job_cron_and_name():
    job = build_news_crawl_job(fetchers=[], store=FakeNewsStore(), hour=0, minute=15)
    assert job.name == "news-crawl"
    assert job.cron == "15 0 * * *"


def test_cleanup_job_runs_purge():
    ran = []
    job = build_news_cleanup_job(purge=lambda: ran.append(True), hour=0, minute=50)
    assert job.name == "news-cleanup"
    assert job.cron == "50 0 * * *"
    job.run()
    assert ran == [True]
