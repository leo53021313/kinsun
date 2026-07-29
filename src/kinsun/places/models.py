"""地點領域模型。

`Place` 是資料表的一列（原始資料，未經任何清洗）；`NearbyPlace` 是查詢結果
（`Place` ＋ 距離）。兩者分開的理由：距離不是店家的屬性，是「相對於某個查詢點」
才成立的東西，塞進 Place 會讓它在 ingest 時無值可填。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    latitude: float
    longitude: float
    category: str
    overture_category: str | None = None
    confidence: float | None = None
    address: str | None = None
    # 3 碼郵遞區號＝行政區指紋（座標可疑剔除用）。Overture 原始值有 3 碼與 6 碼
    # 兩種寫法（110 與 110058），ingest 時就截成 3 碼，查詢端不必再處理。
    postcode: str | None = None
    city: str | None = None
    phone: str | None = None
    ingested_at: float = 0.0


@dataclass(frozen=True)
class NearbyPlace:
    place: Place
    distance_meters: int
