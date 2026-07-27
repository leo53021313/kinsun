"""PlaceStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連獨立測試庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用測試庫上以「成員／排除」關係斷言而互不干擾。

距離斷言留 ±3 公尺容差：Pg 用 SQL 三角函數、Fake 用 Python math，浮點路徑不同，
硬要求逐位相等會讓合約測試變成浮點實作的人質。
"""

from __future__ import annotations

import pytest

from kinsun.places.models import Place
from kinsun.places.store import FakePlaceStore, PgPlaceStore

# 長輩家（中和連城路一帶）。座標與 spec 一致。
ELDER_LAT, ELDER_LON = 25.0, 121.5


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgPlaceStore(request.getfixturevalue("pg_database"))
    return FakePlaceStore()


def _place(ns: str, suffix: str, lat: float, lon: float, category: str, **kw) -> Place:
    return Place(
        place_id=f"{ns}{suffix}",
        name=kw.pop("name", f"店{suffix}"),
        latitude=lat,
        longitude=lon,
        category=category,
        ingested_at=1753600000.0,
        **kw,
    )


def test_list_near_returns_empty_when_nothing_stored(store, ns):
    assert store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=f"{ns}restaurant", radius_meters=1500
    ) == []


def test_save_many_then_list_near_round_trips_with_distance(store, ns):
    cat = f"{ns}restaurant"
    store.save_many([_place(ns, "a", 25.00169, 121.49776, cat, name="小高拉麵")])
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert len(got) == 1
    assert got[0].place.name == "小高拉麵"
    assert 291 <= got[0].distance_meters <= 297


def test_list_near_sorts_by_distance(store, ns):
    cat = f"{ns}restaurant"
    store.save_many(
        [
            _place(ns, "far", 25.010, 121.5, cat, name="遠的"),
            _place(ns, "near", 25.001, 121.5, cat, name="近的"),
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert [n.place.name for n in got] == ["近的", "遠的"]


def test_list_near_excludes_beyond_radius(store, ns):
    cat = f"{ns}restaurant"
    # 約 2.2 公里外——超過 1500 公尺半徑。這條同時守住「不因查無結果而放大半徑」
    # 的前提：store 只負責誠實回報半徑內的東西。
    store.save_many([_place(ns, "outside", 25.020, 121.5, cat, name="板橋分店")])
    assert store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    ) == []


def test_list_near_filters_by_category(store, ns):
    store.save_many(
        [
            _place(ns, "r", 25.001, 121.5, f"{ns}restaurant", name="餐廳"),
            _place(ns, "p", 25.001, 121.5, f"{ns}pharmacy", name="藥局"),
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=f"{ns}pharmacy", radius_meters=1500
    )
    assert [n.place.name for n in got] == ["藥局"]


def test_save_many_is_upsert_on_place_id(store, ns):
    cat = f"{ns}restaurant"
    store.save_many([_place(ns, "a", 25.001, 121.5, cat, name="舊名")])
    store.save_many([_place(ns, "a", 25.001, 121.5, cat, name="新名")])
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert [n.place.name for n in got] == ["新名"]


def test_optional_fields_round_trip(store, ns):
    cat = f"{ns}pharmacy"
    store.save_many(
        [
            _place(
                ns, "a", 25.001, 121.5, cat,
                name="芳碩藥局", postcode="235", city="新北市",
                phone="02-12345678", confidence=0.93, address="連城路100號",
                overture_category="pharmacy",
            )
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )[0].place
    assert (got.postcode, got.city, got.phone) == ("235", "新北市", "02-12345678")
    assert got.confidence == pytest.approx(0.93)


def test_list_postcodes_near_counts_all_categories(store, ns):
    # 行政區指紋的核心：母體是鄰域「全類別」POI，不受 category 過濾影響。
    # 只用候選集算佔比會讓 2% 門檻失效（一筆就可能超過 2%）。
    store.save_many(
        [
            _place(ns, "a", 25.001, 121.5, f"{ns}restaurant", postcode="235"),
            _place(ns, "b", 25.002, 121.5, f"{ns}pharmacy", postcode="235"),
            _place(ns, "c", 25.003, 121.5, f"{ns}restaurant", postcode="112"),
        ]
    )
    counts = dict(
        store.list_postcodes_near(latitude=ELDER_LAT, longitude=ELDER_LON, radius_meters=1500)
    )
    assert counts["235"] == 2
    assert counts["112"] == 1


def test_list_postcodes_near_ignores_rows_without_postcode(store, ns):
    store.save_many([_place(ns, "a", 25.001, 121.5, f"{ns}restaurant")])
    counts = dict(
        store.list_postcodes_near(latitude=ELDER_LAT, longitude=ELDER_LON, radius_meters=1500)
    )
    assert None not in counts
    assert "" not in counts
