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


def test_list_near_breaks_distance_ties_by_place_id(store, ns):
    # 兩筆座標完全相同，distance_meters 必然相等：Pg 對相同 meters 的列不保證
    # 順序穩定，Fake 的 sorted() 雖穩定但只保留插入順序——兩者都得靠 place_id
    # 當 tie-breaker 才會給出一致的順序。刻意先插入字母序較大的 "z"，
    # 若實作退化成只依插入順序，這條會先抓到。
    cat = f"{ns}restaurant"
    store.save_many(
        [
            _place(ns, "z", 25.001, 121.5, cat, name="Z店"),
            _place(ns, "a", 25.001, 121.5, cat, name="A店"),
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert [n.place.place_id for n in got] == [f"{ns}a", f"{ns}z"]


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


def test_save_many_last_wins_on_duplicate_place_id_within_one_call(store, ns):
    # 同一次 save_many() 呼叫內傳入兩筆相同 place_id：FakePlaceStore 用 dict
    # 賦值，天生 last-wins、不會出錯；PgPlaceStore 若讓 Postgres 原生處理同批次
    # 重複 place_id，ON CONFLICT DO UPDATE 在單一語句內對同一列生效兩次會丟
    # CardinalityViolation。兩個 adapter 對同一輸入必須給出相同結果（本檔開頭
    # 合約），故 store 層須自行以 place_id 收斂成 last-wins，且不得受內部分塊
    # 大小影響。
    cat = f"{ns}restaurant"
    store.save_many(
        [
            _place(ns, "a", 25.001, 121.5, cat, name="舊名"),
            _place(ns, "a", 25.001, 121.5, cat, name="新名"),
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert [n.place.name for n in got] == ["新名"]


def test_optional_fields_round_trip(store, ns):
    cat = f"{ns}pharmacy"
    # ⚠️ postcode 帶 ns 前綴（不可用裸的 "235"）：這支測試曾是「兇手」——裸值
    # postcode 在同一組座標寫入後，於連庫 session 內不會被清空，會讓
    # test_list_postcodes_near_counts_all_categories 的精確計數斷言誤算進來。
    store.save_many(
        [
            _place(
                ns, "a", 25.001, 121.5, cat,
                name="芳碩藥局", postcode=f"{ns}235", city="新北市",
                phone="02-12345678", confidence=0.93, address="連城路100號",
                overture_category="pharmacy",
            )
        ]
    )
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )[0].place
    assert (got.postcode, got.city, got.phone) == (f"{ns}235", "新北市", "02-12345678")
    assert got.confidence == pytest.approx(0.93)


def test_list_postcodes_near_counts_all_categories(store, ns):
    # 行政區指紋的核心：母體是鄰域「全類別」POI，不受 category 過濾影響。
    # 只用候選集算佔比會讓 2% 門檻失效（一筆就可能超過 2%）。
    #
    # ⚠️ postcode 也必須帶 ns 前綴，不可用裸的 "235"。本檔其他測試在同一組座標寫入
    # 過 postcode="235"，而 pg_database 是 session 級 fixture、不逐測試清空——
    # 由於本方法**刻意不過濾 category**，靠 category 帶 ns 擋不住那些殘留列，
    # 裸值會讓 counts["235"] 變成 3。真實環境的 postcode 是 3 碼，但那是 ingest 端的
    # 產出慣例，資料表沒有長度限制，測試只需要值彼此不撞。
    store.save_many(
        [
            _place(ns, "a", 25.001, 121.5, f"{ns}restaurant", postcode=f"{ns}235"),
            _place(ns, "b", 25.002, 121.5, f"{ns}pharmacy", postcode=f"{ns}235"),
            _place(ns, "c", 25.003, 121.5, f"{ns}restaurant", postcode=f"{ns}112"),
        ]
    )
    counts = dict(
        store.list_postcodes_near(latitude=ELDER_LAT, longitude=ELDER_LON, radius_meters=1500)
    )
    assert counts[f"{ns}235"] == 2
    assert counts[f"{ns}112"] == 1


def test_purge_older_than_removes_only_stale_rows(store, ns):
    """每月重跑時清掉「上個月符合分類、這個月不符合」的殘留列。

    沒有這個方法的後果：ingest 只 upsert 從不刪除，修了分類規則再重跑時，錯的列
    （例如被誤判成超商的「全家旅店」）會永遠留著。

    ⚠️ `purge_older_than` 依規格是全表操作、不吃 ns 過濾（對齊 ingest.py 的用法：
    整批重新灌入後清掉「這一輪沒寫到」的舊列，本來就該是全域的）。`pg_database`
    是 session 級 fixture、不逐測試清空，本檔其他測試一律用 1753600000.0 這個共用
    預設值（見 `_place()`）；若本測試也沿用同一個時間戳當「舊列」，cutoff 會連帶
    清掉其他測試留下的列，讓 `removed == 1` 的斷言在共用測試庫上失敗。故本測試改用
    遠低於共用預設值、不會被其他測試撞到的極小 epoch 值。
    """
    cat = f"{ns}restaurant"
    store.save_many(
        [Place(place_id=f"{ns}old", name="上個月的", latitude=25.001, longitude=121.5,
               category=cat, ingested_at=1.0)]
    )
    store.save_many(
        [Place(place_id=f"{ns}new", name="這個月的", latitude=25.001, longitude=121.5,
               category=cat, ingested_at=2.0)]
    )
    removed = store.purge_older_than(1.5)
    assert removed == 1
    got = store.list_near(
        latitude=ELDER_LAT, longitude=ELDER_LON, category=cat, radius_meters=1500
    )
    assert [n.place.name for n in got] == ["這個月的"]


def test_list_postcodes_near_ignores_rows_without_postcode(store, ns):
    store.save_many([_place(ns, "a", 25.001, 121.5, f"{ns}restaurant")])
    counts = dict(
        store.list_postcodes_near(latitude=ELDER_LAT, longitude=ELDER_LON, radius_meters=1500)
    )
    assert None not in counts
    assert "" not in counts
