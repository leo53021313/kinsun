"""GreetingPreferenceStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.proactive.preferences import (
    FakeGreetingPreferenceStore,
    GreetingPreference,
    PgGreetingPreferenceStore,
)


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgGreetingPreferenceStore(request.getfixturevalue("pg_database"))
    return FakeGreetingPreferenceStore()


def _pref(elder_id: str, hour: int = 9, minute: int = 30) -> GreetingPreference:
    return GreetingPreference(
        elder_id=elder_id,
        hour=hour,
        minute=minute,
        computed_at=1_784_000_000.0,
        sample_days=7,
        median_minute_of_day=600,
    )


def test_save_then_get_returns_the_preference(store, ns):
    store.save(_pref(f"{ns}e1"))
    got = store.get_for_elder(f"{ns}e1")
    assert got is not None
    assert (got.hour, got.minute, got.sample_days, got.median_minute_of_day) == (9, 30, 7, 600)


def test_get_for_an_unknown_elder_returns_none(store, ns):
    assert store.get_for_elder(f"{ns}nobody") is None


def test_save_is_upsert(store, ns):
    store.save(_pref(f"{ns}e1", hour=8, minute=0))
    store.save(_pref(f"{ns}e1", hour=10, minute=30))
    got = store.get_for_elder(f"{ns}e1")
    assert (got.hour, got.minute) == (10, 30)
    assert len([p for p in store.list_all() if p.elder_id == f"{ns}e1"]) == 1


def test_list_all_spans_elders(store, ns):
    store.save(_pref(f"{ns}e1"))
    store.save(_pref(f"{ns}e2"))
    ids = {p.elder_id for p in store.list_all()}
    assert {f"{ns}e1", f"{ns}e2"} <= ids
