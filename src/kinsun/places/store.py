"""地點持久層：Protocol、Postgres 實作與測試替身。

查詢一律「矩形粗篩（吃索引）→ Haversine 精算（濾成圓）」，兩個 adapter 共用
`geo.py` 的同一份幾何。

⚠️ 本層只負責誠實回報半徑內有什麼，**不做任何品質判斷**。去重、店名清洗、
座標可疑剔除全在 `refine.py`——那些規則會隨著遇到的爛資料持續演進，混進 SQL
就得靠改資料庫查詢來修一個顯示層的問題。
"""

from __future__ import annotations

from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.places.geo import bounding_box, distance_meters
from kinsun.places.models import NearbyPlace, Place

_COLUMNS = (
    "place_id, name, latitude, longitude, category, overture_category, "
    "confidence, address, postcode, city, phone, ingested_at"
)
_COLUMN_COUNT = len(_COLUMNS.split(","))

_UPSERT_SET_CLAUSE = (
    "name = EXCLUDED.name, latitude = EXCLUDED.latitude, "
    "longitude = EXCLUDED.longitude, category = EXCLUDED.category, "
    "overture_category = EXCLUDED.overture_category, "
    "confidence = EXCLUDED.confidence, address = EXCLUDED.address, "
    "postcode = EXCLUDED.postcode, city = EXCLUDED.city, "
    "phone = EXCLUDED.phone, ingested_at = EXCLUDED.ingested_at"
)

# PostgreSQL 單一語句的參數上限是 65535；本表 12 欄，理論上限每句 5461 列。
# 取遠低於上限的保守值分塊——後續任務要把 20～30 萬筆 Overture 資料灌進遠端
# Supabase，逐筆 execute（原寫法）等於 20～30 萬次網路往返＋20～30 萬次 commit，
# 慢到不能用；改成單一交易內、每塊一句多列 INSERT，才把往返與 commit 次數
# 從「列數」降到「列數 / 塊大小」。
_SAVE_MANY_CHUNK_SIZE = 1000


def _upsert_sql(row_count: int) -> str:
    """依實際列數產生多列 VALUES 佔位符（值一律走參數化，不把資料拼進 SQL）。"""
    row_placeholder = f"({', '.join(['%s'] * _COLUMN_COUNT)})"
    values_clause = ", ".join([row_placeholder] * row_count)
    return (
        f"INSERT INTO places ({_COLUMNS}) VALUES {values_clause} "
        f"ON CONFLICT (place_id) DO UPDATE SET {_UPSERT_SET_CLAUSE}"
    )


def _place_params(place: Place) -> tuple:
    return (
        place.place_id,
        place.name,
        place.latitude,
        place.longitude,
        place.category,
        place.overture_category,
        place.confidence,
        place.address,
        place.postcode,
        place.city,
        place.phone,
        place.ingested_at,
    )


class PlaceError(Exception):
    """地點資料存取失敗。"""


class PlaceStore(Protocol):
    def save_many(self, places: list[Place]) -> None: ...
    def list_near(
        self, *, latitude: float, longitude: float, category: str, radius_meters: float
    ) -> list[NearbyPlace]: ...
    def list_postcodes_near(
        self, *, latitude: float, longitude: float, radius_meters: float
    ) -> list[tuple[str, int]]: ...
    def purge_older_than(self, cutoff: float) -> int: ...


# SQL 內聯 Haversine：與 geo.distance_meters 同一條公式。放在 SQL 而非撈回 Python 再算，
# 是為了讓「排序與半徑過濾」在資料庫端完成——候選集可能有數千筆，全撈回來再排很浪費。
_HAVERSINE_SQL = (
    "6371000 * 2 * asin(sqrt("
    "power(sin(radians(%s - latitude) / 2), 2) "
    "+ cos(radians(latitude)) * cos(radians(%s)) "
    "* power(sin(radians(%s - longitude) / 2), 2)))"
)


class PgPlaceStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: PlaceError(f"地點資料存取失敗：{m}"))

    def save_many(self, places: list[Place]) -> None:
        """寫入（upsert）多筆地點。

        ⚠️ 送進 Postgres 前先以 place_id 為鍵收斂成 last-wins，理由不是「避免
        報錯」，是兩件更根本的事：

        1. 合約等價性——本檔開頭明訂「Fake 與 Pg 兩個 adapter 必須對同一情境
           給出相同結果」。FakePlaceStore.save_many 用 dict 賦值，同一次呼叫
           內重複 place_id 天生就是 last-wins；若讓 Postgres 原生處理同一批
           次的重複 place_id，ON CONFLICT DO UPDATE 在單一語句內不能對同一列
           生效兩次，會丟 CardinalityViolation——兩個 adapter 對同一輸入給出
           不同結果，就是違反合約，不是「效能規格外」的邊角案例。
        2. 行為不得隨內部分塊大小飄移——會不會撞上這個錯誤，原本取決於兩筆
           重複 place_id 是否剛好落在同一個 _SAVE_MANY_CHUNK_SIZE 分塊裡；
           那是純內部實作細節，外部行為不該被它決定。
           （這不是新增品質判斷：ON CONFLICT DO UPDATE 的「後者覆蓋前者」
           語意，在分兩次呼叫 save_many() 時舊程式碼就已經在做——見
           test_save_many_is_upsert_on_place_id。在同一批次內沿用同一套
           語意只是把既有語意講完整；真正屬於 refine.py 的是「兩個不同
           place_id 但語意上是同一家店該留誰」那種決策，層次不同。）
        """
        if not places:
            return
        # dict 保序（Python 3.7+），故同時保住「後者勝」與「其餘順序不變」。
        places = list({place.place_id: place for place in places}.values())
        with self._db.transaction() as tx:
            for start in range(0, len(places), _SAVE_MANY_CHUNK_SIZE):
                chunk = places[start : start + _SAVE_MANY_CHUNK_SIZE]
                params = tuple(value for place in chunk for value in _place_params(place))
                tx.execute(_upsert_sql(len(chunk)), params)

    def list_near(
        self, *, latitude: float, longitude: float, category: str, radius_meters: float
    ) -> list[NearbyPlace]:
        lat_lo, lat_hi, lon_lo, lon_hi = bounding_box(latitude, longitude, radius_meters)
        rows = self._db.query(
            f"SELECT * FROM (SELECT {_COLUMNS}, {_HAVERSINE_SQL} AS meters FROM places "
            "WHERE category = %s AND latitude BETWEEN %s AND %s "
            "AND longitude BETWEEN %s AND %s) t "
            # place_id 當 tie-breaker：PostgreSQL 對 meters 相同的列不保證穩定順序，
            # 與 FakePlaceStore（Python 穩定排序＋同一組 key）維持合約等價。
            "WHERE meters <= %s ORDER BY meters, place_id",
            (
                latitude,
                latitude,
                longitude,
                category,
                lat_lo,
                lat_hi,
                lon_lo,
                lon_hi,
                radius_meters,
            ),
        )
        return [NearbyPlace(Place(*row[:-1]), round(row[-1])) for row in rows]

    def list_postcodes_near(
        self, *, latitude: float, longitude: float, radius_meters: float
    ) -> list[tuple[str, int]]:
        lat_lo, lat_hi, lon_lo, lon_hi = bounding_box(latitude, longitude, radius_meters)
        rows = self._db.query(
            f"SELECT postcode, count(*) FROM (SELECT postcode, {_HAVERSINE_SQL} AS meters "
            "FROM places WHERE postcode IS NOT NULL AND postcode <> '' "
            "AND latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s) t "
            "WHERE meters <= %s GROUP BY postcode",
            (latitude, latitude, longitude, lat_lo, lat_hi, lon_lo, lon_hi, radius_meters),
        )
        return [(row[0], row[1]) for row in rows]

    def purge_older_than(self, cutoff: float) -> int:
        """刪掉 `ingested_at` 早於 cutoff 的列，回傳刪除筆數。

        供每月重跑 ingest 時清除「上個月符合分類、這個月不符合」的殘留列——
        `ingest.py` 只 upsert 從不刪除，修了 `categories.py` 的規則再重跑時，
        錯誤分類的舊列（例如被誤判成超商的「全家旅店」）不會自動消失。
        動詞用 `purge_older_than` 是照全庫既有慣例（見其他 store 的同名方法）。
        """
        row = self._db.query_one(
            "WITH removed AS (DELETE FROM places WHERE ingested_at < %s RETURNING 1) "
            "SELECT count(*) FROM removed",
            (cutoff,),
        )
        return row[0] if row else 0


class FakePlaceStore:
    """PlaceStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._places: dict[str, Place] = {}

    def save_many(self, places: list[Place]) -> None:
        # dict 賦值天生 last-wins：同一次呼叫內重複 place_id 時，後者覆蓋前者，
        # 與 PgPlaceStore.save_many 收斂後的語意等價，無需另外處理。
        for place in places:
            self._places[place.place_id] = place

    def _within(self, latitude: float, longitude: float, radius_meters: float):
        for place in self._places.values():
            meters = distance_meters(latitude, longitude, place.latitude, place.longitude)
            if meters <= radius_meters:
                yield place, meters

    def list_near(
        self, *, latitude: float, longitude: float, category: str, radius_meters: float
    ) -> list[NearbyPlace]:
        found = [
            NearbyPlace(place, meters)
            for place, meters in self._within(latitude, longitude, radius_meters)
            if place.category == category
        ]
        # place_id 當 tie-breaker：與 PgPlaceStore 的 ORDER BY meters, place_id 對齊，
        # 兩個 adapter 在距離相同時才會給出一致的順序（合約要求的等價性）。
        return sorted(found, key=lambda n: (n.distance_meters, n.place.place_id))

    def list_postcodes_near(
        self, *, latitude: float, longitude: float, radius_meters: float
    ) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for place, _ in self._within(latitude, longitude, radius_meters):
            if place.postcode:
                counts[place.postcode] = counts.get(place.postcode, 0) + 1
        return list(counts.items())

    def purge_older_than(self, cutoff: float) -> int:
        stale = [place_id for place_id, place in self._places.items() if place.ingested_at < cutoff]
        for place_id in stale:
            del self._places[place_id]
        return len(stale)
