"""最近新聞工具：讀話題新聞表（news_items）回口語標題清單。

消費端工具（D-74 後續）：爬蟲與資料表在 news/（生產端），此處只讀不寫。
視窗取 3 天而非問候端的 1 天——爬蟲一晚失敗時聊天仍有料可講。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from kinsun.llm import ToolSpec
from kinsun.news.store import NewsError, NewsStore

logger = logging.getLogger("kinsun.tools.news")

NEWS_SPEC = ToolSpec(
    name="get_news",
    description=(
        "取得最近幾天的新聞標題（衛福部與台灣新聞）。當長輩問最近有什麼新聞、想聊時事話題時使用。"
    ),
    parameters={"type": "object", "properties": {}},
)

_EMPTY_REPLY = "目前沒有最新的新聞資料，晚一點再問問我。"
_FAILURE_REPLY = "（新聞資料暫時讀不到，請稍後再試）"


def build_news_handler(
    store: NewsStore,
    *,
    clock: Callable[[], datetime],
    window_days: int = 3,
    limit: int = 5,
) -> Callable[[dict], str]:
    def handler(_args: dict) -> str:
        since = clock().timestamp() - window_days * 86400
        try:
            items = store.list_recent(since=since)
        except NewsError:
            logger.warning("get_news 讀取新聞失敗，回口語降級提示")
            return _FAILURE_REPLY
        if not items:
            return _EMPTY_REPLY
        lines = [f"（{item.publisher}）{item.title}" for item in items[:limit]]
        return "最近的新聞有：" + "；".join(lines) + "。"

    return handler
