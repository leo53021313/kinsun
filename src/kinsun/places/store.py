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
        for place in places:
            self._db.execute(
                f"INSERT INTO places ({_COLUMNS}) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (place_id) DO UPDATE SET "
                "name = EXCLUDED.name, latitude = EXCLUDED.latitude, "
                "longitude = EXCLUDED.longitude, category = EXCLUDED.category, "
                "overture_category = EXCLUDED.overture_category, "
                "confidence = EXCLUDED.confidence, address = EXCLUDED.address, "
                "postcode = EXCLUDED.postcode, city = EXCLUDED.city, "
                "phone = EXCLUDED.phone, ingested_at = EXCLUDED.ingested_at",
                (
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
                ),
            )

    def list_near(
        self, *, latitude: float, longitude: float, category: str, radius_meters: float
    ) -> list[NearbyPlace]:
        lat_lo, lat_hi, lon_lo, lon_hi = bounding_box(latitude, longitude, radius_meters)
        rows = self._db.query(
            f"SELECT * FROM (SELECT {_COLUMNS}, {_HAVERSINE_SQL} AS meters FROM places "
            "WHERE category = %s AND latitude BETWEEN %s AND %s "
            "AND longitude BETWEEN %s AND %s) t "
            "WHERE meters <= %s ORDER BY meters",
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


class FakePlaceStore:
    """PlaceStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._places: dict[str, Place] = {}

    def save_many(self, places: list[Place]) -> None:
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
        return sorted(found, key=lambda n: n.distance_meters)

    def list_postcodes_near(
        self, *, latitude: float, longitude: float, radius_meters: float
    ) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for place, _ in self._within(latitude, longitude, radius_meters):
            if place.postcode:
                counts[place.postcode] = counts.get(place.postcode, 0) + 1
        return list(counts.items())
