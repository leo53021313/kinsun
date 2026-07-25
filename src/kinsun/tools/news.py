"""最近新聞工具：讀話題新聞表（news_items）回口語標題清單與內文。

消費端工具（D-74 後續）：爬蟲與資料表在 news/（生產端），此處只讀新聞、只寫提及紀錄。
視窗取 3 天而非問候端舊有的 1 天——爬蟲一晚失敗時聊天仍有料可講。

多樣性設計（D-74 ①）：候選依 published_at 新→舊排序（同批爬取 retrieved_at 全同值，
發布時間才分得出新舊），前 pool_size 則為池、隨機取 limit 則；配合提及紀錄
（news_mentions）排除「已對這位長輩給過的」，全被排除時回退用全部——寧可重複、
不可沒話講。

注入面防線（D-74 ②）：標題與內文出站前壓平空白、去反引號、截長度——外部媒體
文字是資料不是指令，至少不讓它夾帶換行與 code fence 假冒訊息結構。
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import datetime

from kinsun.llm import ToolSpec
from kinsun.news.mentions import NewsMentionStore
from kinsun.news.models import NewsItem
from kinsun.news.store import NewsError, NewsStore
from kinsun.tools.registry import ToolInvocationContext

logger = logging.getLogger("kinsun.tools.news")

NEWS_SPEC = ToolSpec(
    name="get_news",
    description=(
        "取得最近幾天的新聞標題（衛福部與台灣新聞）。"
        "當長輩問最近有什麼新聞、想聊時事話題、或你主動找開場話題時使用；"
        "若知道她的興趣，可帶 topic 關鍵字挑相關的新聞。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "想找的主題關鍵字（如「疫苗」「颱風」）；留空＝不限主題",
            }
        },
    },
)

NEWS_DETAIL_SPEC = ToolSpec(
    name="get_news_detail",
    description=(
        "取得某一則新聞的詳細內容。長輩對 get_news 回覆中的某則新聞有興趣、"
        "想多聽一點時使用；title 帶那則新聞的標題（或標題中的幾個字）。"
    ),
    parameters={
        "type": "object",
        "properties": {"title": {"type": "string", "description": "新聞標題或標題關鍵字"}},
        "required": ["title"],
    },
)

_EMPTY_REPLY = "目前沒有最新的新聞資料，晚一點再問問我。"
_FAILURE_REPLY = "（新聞資料暫時讀不到，請稍後再試）"


def _sanitize(text: str, max_chars: int) -> str:
    """出站清洗：壓平空白、去反引號、截長度（外部文字是資料不是指令）。"""
    cleaned = " ".join(text.replace("`", "").split())
    if len(cleaned) > max_chars:
        return cleaned[: max_chars - 1] + "…"
    return cleaned


def _freshness(item: NewsItem) -> float:
    return item.published_at if item.published_at is not None else item.retrieved_at


def _load_recent(
    store: NewsStore, *, clock: Callable[[], datetime], window_days: int
) -> list[NewsItem] | None:
    """讀近幾天新聞；讀取失敗回 None（呼叫端回口語降級提示）。"""
    since = clock().timestamp() - window_days * 86400
    try:
        return store.list_recent(since=since)
    except NewsError:
        logger.warning("新聞工具讀取 news_items 失敗，回口語降級提示")
        return None


def _known_mentions(mentions: NewsMentionStore | None, elder_id: str) -> set[str]:
    if mentions is None or not elder_id:
        return set()
    try:
        return mentions.list_for_elder(elder_id)
    except NewsError:
        logger.warning("提及紀錄讀取失敗，本次不排除已提過的新聞")
        return set()


def _record_mentions(
    mentions: NewsMentionStore | None,
    elder_id: str,
    items: list[NewsItem],
    *,
    clock: Callable[[], datetime],
) -> None:
    if mentions is None or not elder_id:
        return
    now = clock().timestamp()
    try:
        for item in items:
            mentions.record(elder_id, item.news_item_id, mentioned_at=now)
    except NewsError:
        logger.warning("提及紀錄寫入失敗，不影響本次回覆")


def build_news_handler(
    store: NewsStore,
    *,
    clock: Callable[[], datetime],
    mentions: NewsMentionStore | None = None,
    rng: random.Random | None = None,
    window_days: int = 3,
    limit: int = 5,
    pool_size: int = 10,
) -> Callable[[dict, ToolInvocationContext | None], str]:
    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        items = _load_recent(store, clock=clock, window_days=window_days)
        if items is None:
            return _FAILURE_REPLY
        topic = (arguments.get("topic") or "").strip()
        if topic:
            items = [i for i in items if topic in i.title or topic in i.content]
        elder_id = context.elder_id if context else ""
        seen = _known_mentions(mentions, elder_id)
        fresh = [i for i in items if i.news_item_id not in seen]
        candidates = sorted(fresh or items, key=_freshness, reverse=True)
        if not candidates:
            return _EMPTY_REPLY
        pool = candidates[:pool_size]
        if len(pool) > limit:
            chosen = (rng or random).sample(pool, limit)
            chosen.sort(key=_freshness, reverse=True)
        else:
            chosen = pool
        _record_mentions(mentions, elder_id, chosen, clock=clock)
        lines = [f"（{_sanitize(i.publisher, 30)}）{_sanitize(i.title, 100)}" for i in chosen]
        return "最近的新聞有：" + "；".join(lines) + "。"

    return handler


def build_news_detail_handler(
    store: NewsStore,
    *,
    clock: Callable[[], datetime],
    mentions: NewsMentionStore | None = None,
    window_days: int = 3,
    max_chars: int = 800,
) -> Callable[[dict, ToolInvocationContext | None], str]:
    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        query = (arguments.get("title") or "").strip()
        if not query:
            return "（請告訴我想聽哪一則新聞的標題）"
        items = _load_recent(store, clock=clock, window_days=window_days)
        if items is None:
            return _FAILURE_REPLY
        match = next((i for i in items if query in i.title or i.title in query), None)
        if match is None:
            shown = _sanitize(query, 50)
            return f"（找不到標題有「{shown}」的新聞，可以先用 get_news 看看最近有哪些）"
        elder_id = context.elder_id if context else ""
        _record_mentions(mentions, elder_id, [match], clock=clock)
        title = _sanitize(match.title, 100)
        publisher = _sanitize(match.publisher, 30)
        content = _sanitize(match.content, max_chars)
        return f"（{publisher}）{title}：{content}"

    return handler
