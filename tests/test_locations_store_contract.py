"""LocationStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連獨立測試庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.locations.store import ElderLocation, FakeLocationStore, PgLocationStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgLocationStore(request.getfixturevalue("pg_database"))
    return FakeLocationStore()


def test_get_for_elder_returns_none_when_never_recorded(store, ns):
    assert store.get_for_elder(f"{ns}e1") is None


def test_save_then_get_round_trips(store, ns):
    store.save(ElderLocation(f"{ns}e1", "台南市", 1752739200.0))
    assert store.get_for_elder(f"{ns}e1") == ElderLocation(f"{ns}e1", "台南市", 1752739200.0)


def test_save_is_upsert_keeping_only_latest(store, ns):
    # 「覆寫式」的核心斷言：同一位長輩存兩次只留最新一筆，不累積行蹤軌跡。
    store.save(ElderLocation(f"{ns}e1", "台南市", 1752739200.0))
    store.save(ElderLocation(f"{ns}e1", "高雄市", 1752742800.0))
    assert store.get_for_elder(f"{ns}e1") == ElderLocation(f"{ns}e1", "高雄市", 1752742800.0)


def test_one_elder_location_does_not_leak_to_another(store, ns):
    store.save(ElderLocation(f"{ns}e1", "台南市", 1752739200.0))
    assert store.get_for_elder(f"{ns}e2") is None


def test_save_and_get_coords(store, ns):
    store.save(ElderLocation(f"{ns}e1", "台南市", 1752739200.0, 22.99, 120.21))
    got = store.get_for_elder(f"{ns}e1")
    assert got == ElderLocation(f"{ns}e1", "台南市", 1752739200.0, 22.99, 120.21)


def test_coords_may_be_absent(store, ns):
    # 既有列的情形：PR #55 寫入的資料沒有座標，ALTER 後為 NULL。
    store.save(ElderLocation(f"{ns}e1", "台南市", 1752739200.0))
    got = store.get_for_elder(f"{ns}e1")
    assert got is not None
    assert got.latitude is None
    assert got.longitude is None
