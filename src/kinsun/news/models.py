"""話題新聞的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsItem:
    news_item_id: str
    source_id: str  # 來源識別碼，如 "mohw"、"news_api"
    title: str
    url: str
    publisher: str
    content: str
    published_at: float | None  # 新聞發布時間（epoch 秒）；來源未提供則為 None
    retrieved_at: float  # 本次抓取時間（epoch 秒）
