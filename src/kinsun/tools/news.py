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
from typing import Protocol

from kinsun.llm import ToolSpec
from kinsun.news.mentions import NewsMentionStore
from kinsun.news.models import NewsItem
from kinsun.news.store import NewsError, NewsStore
from kinsun.tools.registry import ToolInvocationContext
from kinsun.turn_context import record_source

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


def _parse_blocked(blocked_keywords: str) -> list[str]:
    return [kw.strip() for kw in blocked_keywords.split(",") if kw.strip()]


def _drop_blocked(items: list[NewsItem], blocked: list[str]) -> list[NewsItem]:
    """負面新聞過濾（Leo 2026-07-25）：標題或內文含排除關鍵字整則不給——
    兇殺、事故類話題不適合金孫拿來開場。"""
    if not blocked:
        return items
    return [i for i in items if not any(kw in i.title or kw in i.content for kw in blocked)]


def _region_token(locations: LocationStoreLike | None, elder_id: str) -> str:
    """長輩所在縣市的比對詞（取地名前兩字，如「台南市東區」→「台南」）。

    位置是錦上添花：沒有 store、沒有 elder、沒有位置列、或讀取失敗，一律回空字串
    （不加權，行為同無在地化）。
    """
    if locations is None or not elder_id:
        return ""
    try:
        row = locations.get_for_elder(elder_id)
    except Exception:  # noqa: BLE001 - 位置讀取失敗不可擋新聞工具
        logger.warning("讀取長輩位置失敗，本次不做在地化加權")
        return ""
    if row is None or len(row.place) < 2:
        return ""
    return row.place[:2]


class LocationStoreLike(Protocol):
    def get_for_elder(self, elder_id: str) -> object | None: ...


def _as_text(value) -> str:
    """把模型送來的文字參數轉成字串。

    ⚠️ 實測：模型偶爾把 `topic` 送成清單（`["健康"]`），原本的 `(value or "").strip()`
    會拋 `AttributeError: 'list' object has no attribute 'strip'`，被 registry 的
    except 吞成一句「工具執行失敗」——長輩問了新聞卻拿不到，而且查不出原因。
    非字串一律 `str()` 後再 strip，能救的就救。
    """
    if value is None:
        return ""
    return (value if isinstance(value, str) else str(value)).strip()


def build_news_handler(
    store: NewsStore,
    *,
    clock: Callable[[], datetime],
    mentions: NewsMentionStore | None = None,
    locations: LocationStoreLike | None = None,
    rng: random.Random | None = None,
    blocked_keywords: str = "",
    window_days: int = 3,
    limit: int = 5,
    pool_size: int = 10,
    local_slots: int = 2,
) -> Callable[[dict, ToolInvocationContext | None], str]:
    blocked = _parse_blocked(blocked_keywords)

    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        items = _load_recent(store, clock=clock, window_days=window_days)
        if items is None:
            return _FAILURE_REPLY
        items = _drop_blocked(items, blocked)
        topic = _as_text(arguments.get("topic"))
        if topic:
            items = [i for i in items if topic in i.title or topic in i.content]
        elder_id = context.elder_id if context else ""
        seen = _known_mentions(mentions, elder_id)
        fresh = [i for i in items if i.news_item_id not in seen]
        candidates = sorted(fresh or items, key=_freshness, reverse=True)
        if not candidates:
            return _EMPTY_REPLY
        # 在地化（Leo 2026-07-25）：標題含長輩所在縣市的新聞保證入選（最多
        # local_slots 則）——在地新聞稀少，從全部候選找、不受前 pool_size 池限制。
        region = _region_token(locations, elder_id)
        local_hits = [i for i in candidates if region in i.title][:local_slots] if region else []
        rest = [i for i in candidates if i not in local_hits]
        pool = rest[:pool_size]
        remaining_slots = limit - len(local_hits)
        if len(pool) > remaining_slots:
            picked = (rng or random).sample(pool, max(remaining_slots, 0))
        else:
            picked = pool
        chosen = sorted(local_hits + picked, key=_freshness, reverse=True)
        _record_mentions(mentions, elder_id, chosen, clock=clock)
        # 本輪來源登記（2026-07-26 實測 S4）：媒體名是真的來源，金孫轉述時講出來
        # 屬合法引用，出站的冒名防線不該攔它。
        for item in chosen:
            record_source(item.publisher)
        lines = [f"（{_sanitize(i.publisher, 30)}）{_sanitize(i.title, 100)}" for i in chosen]
        return "最近的新聞有：" + "；".join(lines) + "。"

    return handler


def build_news_detail_handler(
    store: NewsStore,
    *,
    clock: Callable[[], datetime],
    mentions: NewsMentionStore | None = None,
    blocked_keywords: str = "",
    window_days: int = 3,
    max_chars: int = 800,
) -> Callable[[dict, ToolInvocationContext | None], str]:
    blocked = _parse_blocked(blocked_keywords)

    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        query = _as_text(arguments.get("title"))
        if not query:
            return "（請告訴我想聽哪一則新聞的標題）"
        items = _load_recent(store, clock=clock, window_days=window_days)
        if items is None:
            return _FAILURE_REPLY
        items = _drop_blocked(items, blocked)
        match = next((i for i in items if query in i.title or i.title in query), None)
        if match is None:
            shown = _sanitize(query, 50)
            return f"（找不到標題有「{shown}」的新聞，可以先用 get_news 看看最近有哪些）"
        elder_id = context.elder_id if context else ""
        _record_mentions(mentions, elder_id, [match], clock=clock)
        record_source(match.publisher)
        title = _sanitize(match.title, 100)
        publisher = _sanitize(match.publisher, 30)
        content = _sanitize(match.content, max_chars)
        return f"（{publisher}）{title}：{content}"

    return handler
