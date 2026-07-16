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


def _pref(
    elder_id: str,
    hour: int = 9,
    minute: int = 30,
    computed_at: float = 1_784_000_000.0,
    sample_days: int = 7,
    median_minute_of_day: int = 600,
) -> GreetingPreference:
    return GreetingPreference(
        elder_id=elder_id,
        hour=hour,
        minute=minute,
        computed_at=computed_at,
        sample_days=sample_days,
        median_minute_of_day=median_minute_of_day,
    )


def test_save_then_get_returns_the_preference(store, ns):
    store.save(_pref(f"{ns}e1"))
    got = store.get_for_elder(f"{ns}e1")
    assert got is not None
    assert (got.hour, got.minute, got.sample_days, got.median_minute_of_day) == (9, 30, 7, 600)


def test_get_for_an_unknown_elder_returns_none(store, ns):
    assert store.get_for_elder(f"{ns}nobody") is None


def test_save_is_upsert(store, ns):
    """重算後每一個非鍵欄位都必須被覆蓋，可解釋性欄位不得凍結在第一次的值。

    夜間批次第二次跑，某長輩從 08:00 調成 10:30。若只更新 hour／minute，後台會顯示
    「憑 7 天資料、中位 600 分算出 10:30」——但 10:30 是另一批資料算的，連
    computed_at 都還停在當初，看不出這數字多舊。故兩次 save 的五個非鍵欄位全給
    不同值，逐欄釘死覆蓋行為。
    """
    first = _pref(
        f"{ns}e1",
        hour=8,
        minute=0,
        computed_at=1_784_000_000.0,
        sample_days=7,
        median_minute_of_day=600,
    )
    second = _pref(
        f"{ns}e1",
        hour=10,
        minute=30,
        computed_at=1_784_086_400.0,
        sample_days=14,
        median_minute_of_day=630,
    )
    # 前提：兩者除了 elder_id（衝突鍵）外每欄都不同，否則本測試對該欄沒有鑑別力。
    assert all(
        getattr(first, f) != getattr(second, f)
        for f in ("hour", "minute", "computed_at", "sample_days", "median_minute_of_day")
    )

    store.save(first)
    store.save(second)

    got = store.get_for_elder(f"{ns}e1")
    assert got == second
    assert len([p for p in store.list_all() if p.elder_id == f"{ns}e1"]) == 1


def test_list_all_spans_elders(store, ns):
    store.save(_pref(f"{ns}e1"))
    store.save(_pref(f"{ns}e2"))
    ids = {p.elder_id for p in store.list_all()}
    assert {f"{ns}e1", f"{ns}e2"} <= ids
