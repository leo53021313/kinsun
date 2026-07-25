from __future__ import annotations

import random
from datetime import UTC, datetime

from kinsun.news.mentions import FakeNewsMentionStore
from kinsun.news.models import NewsItem
from kinsun.news.store import FakeNewsStore, NewsError
from kinsun.tools.news import (
    NEWS_DETAIL_SPEC,
    NEWS_SPEC,
    build_news_detail_handler,
    build_news_handler,
)
from kinsun.tools.registry import ToolInvocationContext

_NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)


def _clock() -> datetime:
    return _NOW


def _item(
    news_item_id: str,
    *,
    title: str,
    retrieved_at: float | None = None,
    published_at: float | None = None,
    publisher: str = "衛生福利部",
    content: str = "內文",
):
    retrieved = retrieved_at if retrieved_at is not None else _NOW.timestamp() - 3600
    return NewsItem(
        news_item_id=news_item_id,
        source_id="mohw",
        title=title,
        url=f"https://example.com/{news_item_id}",
        publisher=publisher,
        content=content,
        published_at=published_at if published_at is not None else retrieved,
        retrieved_at=retrieved,
    )


def _ctx(elder_id: str = "e1") -> ToolInvocationContext:
    return ToolInvocationContext("", elder_id, False)


# --- get_news ---


def test_spec_has_name_and_optional_topic_parameter():
    assert NEWS_SPEC.name == "get_news"
    assert "topic" in NEWS_SPEC.parameters["properties"]
    assert NEWS_SPEC.parameters.get("required", []) == []


def test_handler_returns_recent_titles_with_publisher():
    store = FakeNewsStore()
    store.save(_item("n1", title="長者防跌新措施"))
    store.save(_item("n2", title="流感疫苗開打", publisher="測試媒體"))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({}, None)
    assert "長者防跌新措施" in reply
    assert "流感疫苗開打" in reply
    assert "衛生福利部" in reply
    assert "測試媒體" in reply


def test_handler_orders_by_published_at_newest_first():
    store = FakeNewsStore()
    base = _NOW.timestamp()
    # retrieved_at 全部相同（同一批爬取），published_at 才是排序鍵（D-74 ①）。
    store.save(_item("old", title="舊聞", retrieved_at=base, published_at=base - 86400 * 2))
    store.save(_item("new", title="今日新聞", retrieved_at=base, published_at=base - 60))
    store.save(_item("mid", title="昨日新聞", retrieved_at=base, published_at=base - 86400))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({}, None)
    assert reply.index("今日新聞") < reply.index("昨日新聞") < reply.index("舊聞")


def test_handler_samples_five_from_pool_with_injected_rng():
    store = FakeNewsStore()
    for i in range(8):
        store.save(_item(f"n{i}", title=f"新聞{i}"))
    handler = build_news_handler(store, clock=_clock, rng=random.Random(0))
    reply = handler({}, None)
    assert reply.count("（衛生福利部）") == 5


def test_handler_filters_by_topic_keyword():
    store = FakeNewsStore()
    store.save(_item("n1", title="流感疫苗開打"))
    store.save(_item("n2", title="公園健走活動"))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({"topic": "疫苗"}, None)
    assert "流感疫苗開打" in reply
    assert "公園健走活動" not in reply


def test_handler_excludes_items_already_mentioned_to_this_elder():
    store = FakeNewsStore()
    store.save(_item("n1", title="提過的新聞"))
    store.save(_item("n2", title="沒提過的新聞"))
    mentions = FakeNewsMentionStore()
    mentions.record("e1", "n1", mentioned_at=_NOW.timestamp() - 86400)
    handler = build_news_handler(store, clock=_clock, mentions=mentions)
    reply = handler({}, _ctx("e1"))
    assert "沒提過的新聞" in reply
    assert "提過的新聞」" not in reply and "（衛生福利部）提過的新聞" not in reply


def test_handler_repeats_when_everything_was_mentioned():
    # 全部都提過＝寧可重複、不可沒話講：回退用全部候選。
    store = FakeNewsStore()
    store.save(_item("n1", title="唯一一則"))
    mentions = FakeNewsMentionStore()
    mentions.record("e1", "n1", mentioned_at=_NOW.timestamp() - 86400)
    handler = build_news_handler(store, clock=_clock, mentions=mentions)
    assert "唯一一則" in handler({}, _ctx("e1"))


def test_handler_records_served_items_for_elder():
    store = FakeNewsStore()
    store.save(_item("n1", title="會被記錄的新聞"))
    mentions = FakeNewsMentionStore()
    handler = build_news_handler(store, clock=_clock, mentions=mentions)
    handler({}, _ctx("e1"))
    assert mentions.list_for_elder("e1") == {"n1"}


def test_handler_without_elder_context_serves_but_does_not_record():
    store = FakeNewsStore()
    store.save(_item("n1", title="匿名情境"))
    mentions = FakeNewsMentionStore()
    handler = build_news_handler(store, clock=_clock, mentions=mentions)
    reply = handler({}, None)
    assert "匿名情境" in reply
    assert mentions.list_for_elder("e1") == set()


def test_handler_mentions_failure_degrades_but_still_replies():
    class _ExplodingMentions(FakeNewsMentionStore):
        def list_for_elder(self, elder_id):
            raise NewsError("news_mentions 表掛了")

        def record(self, elder_id, news_item_id, *, mentioned_at):
            raise NewsError("news_mentions 表掛了")

    store = FakeNewsStore()
    store.save(_item("n1", title="照常給料"))
    handler = build_news_handler(store, clock=_clock, mentions=_ExplodingMentions())
    assert "照常給料" in handler({}, _ctx("e1"))


def test_handler_sanitizes_title_whitespace_and_backticks():
    store = FakeNewsStore()
    store.save(_item("n1", title="有換行\n和```反引號 的標題"))
    handler = build_news_handler(store, clock=_clock)
    reply = handler({}, None)
    assert "有換行 和反引號 的標題" in reply
    assert "\n" not in reply
    assert "`" not in reply


def test_handler_returns_friendly_message_when_empty():
    handler = build_news_handler(FakeNewsStore(), clock=_clock)
    assert handler({}, None) == "目前沒有最新的新聞資料，晚一點再問問我。"


def test_handler_degrades_to_friendly_message_on_store_failure():
    class _ExplodingStore(FakeNewsStore):
        def list_recent(self, *, since):
            raise NewsError("news_items 表掛了")

    handler = build_news_handler(_ExplodingStore(), clock=_clock)
    assert handler({}, None) == "（新聞資料暫時讀不到，請稍後再試）"


# --- get_news_detail ---


def test_detail_spec_requires_title():
    assert NEWS_DETAIL_SPEC.name == "get_news_detail"
    assert NEWS_DETAIL_SPEC.parameters["required"] == ["title"]


def test_detail_returns_content_for_matching_title():
    store = FakeNewsStore()
    store.save(
        _item("n1", title="長者防跌新措施", content="衛福部宣布防跌計畫，內容包含居家改善。")
    )
    handler = build_news_detail_handler(store, clock=_clock)
    reply = handler({"title": "防跌"}, None)
    assert "長者防跌新措施" in reply
    assert "居家改善" in reply


def test_detail_clips_long_content():
    store = FakeNewsStore()
    store.save(_item("n1", title="很長的新聞", content="字" * 2000))
    handler = build_news_detail_handler(store, clock=_clock, max_chars=800)
    reply = handler({"title": "很長的新聞"}, None)
    assert len(reply) < 900
    assert reply.endswith("…")


def test_detail_not_found_returns_friendly_message():
    handler = build_news_detail_handler(FakeNewsStore(), clock=_clock)
    reply = handler({"title": "不存在的標題"}, None)
    assert "找不到" in reply


def test_detail_records_mention_for_elder():
    store = FakeNewsStore()
    store.save(_item("n1", title="有興趣的新聞"))
    mentions = FakeNewsMentionStore()
    handler = build_news_detail_handler(store, clock=_clock, mentions=mentions)
    handler({"title": "有興趣的新聞"}, _ctx("e1"))
    assert mentions.list_for_elder("e1") == {"n1"}


# --- 選題調校（Leo 2026-07-25 核可：負面過濾＋在地化）---


class _FakeLocations:
    def __init__(self, place: str | None) -> None:
        self._place = place

    def get_for_elder(self, elder_id: str):
        from kinsun.locations.store import ElderLocation

        if self._place is None:
            return None
        return ElderLocation(elder_id=elder_id, place=self._place, recorded_at=0.0)


def test_handler_excludes_items_with_blocked_keywords():
    store = FakeNewsStore()
    store.save(_item("n1", title="公園健走活動"))
    store.save(_item("n2", title="市區驚傳兇殺案"))
    handler = build_news_handler(store, clock=_clock, blocked_keywords="兇殺,命案")
    reply = handler({}, None)
    assert "公園健走活動" in reply
    assert "兇殺" not in reply


def test_handler_blocked_keywords_blank_keeps_everything():
    store = FakeNewsStore()
    store.save(_item("n1", title="市區驚傳兇殺案"))
    handler = build_news_handler(store, clock=_clock, blocked_keywords="")
    assert "兇殺" in handler({}, None)


def test_detail_refuses_blocked_item():
    store = FakeNewsStore()
    store.save(_item("n1", title="市區驚傳兇殺案", content="細節"))
    handler = build_news_detail_handler(store, clock=_clock, blocked_keywords="兇殺")
    assert "找不到" in handler({"title": "兇殺案"}, None)


def test_handler_guarantees_local_news_for_elder_location():
    store = FakeNewsStore()
    base = _NOW.timestamp()
    # 十多則非在地新聞把池子塞滿；在地那則發布最早、照理擠不進前 10 池。
    for i in range(12):
        store.save(_item(f"n{i}", title=f"全國新聞{i}", published_at=base - i * 60))
    store.save(_item("local", title="台南美食節登場", published_at=base - 86400))
    handler = build_news_handler(
        store, clock=_clock, locations=_FakeLocations("台南市東區"), rng=random.Random(0)
    )
    assert "台南美食節登場" in handler({}, _ctx("e1"))


def test_handler_without_location_row_behaves_normally():
    store = FakeNewsStore()
    store.save(_item("n1", title="全國新聞"))
    handler = build_news_handler(store, clock=_clock, locations=_FakeLocations(None))
    assert "全國新聞" in handler({}, _ctx("e1"))


def test_handler_location_store_failure_degrades():
    class _Exploding:
        def get_for_elder(self, elder_id):
            raise RuntimeError("elder_locations 表掛了")

    store = FakeNewsStore()
    store.save(_item("n1", title="照常給料的新聞"))
    handler = build_news_handler(store, clock=_clock, locations=_Exploding())
    assert "照常給料的新聞" in handler({}, _ctx("e1"))
