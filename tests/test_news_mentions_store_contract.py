"""NewsMentionStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言以 `ns` 前綴 scope 到本測試
自己的資料，才能在共用真庫上互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.news.mentions import FakeNewsMentionStore, PgNewsMentionStore


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgNewsMentionStore(request.getfixturevalue("pg_database"))
    return FakeNewsMentionStore()


def test_record_then_list_for_elder_returns_mentioned_ids(store, ns):
    store.record(f"{ns}e1", f"{ns}n1", mentioned_at=100.0)
    store.record(f"{ns}e1", f"{ns}n2", mentioned_at=200.0)
    store.record(f"{ns}e2", f"{ns}n3", mentioned_at=300.0)
    assert store.list_for_elder(f"{ns}e1") == {f"{ns}n1", f"{ns}n2"}
    assert store.list_for_elder(f"{ns}e2") == {f"{ns}n3"}


def test_record_same_pair_twice_keeps_single_row(store, ns):
    store.record(f"{ns}e1", f"{ns}n1", mentioned_at=100.0)
    store.record(f"{ns}e1", f"{ns}n1", mentioned_at=200.0)  # 不應拋錯、不應重複
    assert store.list_for_elder(f"{ns}e1") == {f"{ns}n1"}


def test_list_for_elder_without_mentions_is_empty(store, ns):
    assert store.list_for_elder(f"{ns}nobody") == set()


def test_purge_older_than_removes_only_expired(store, ns):
    store.record(f"{ns}e1", f"{ns}old", mentioned_at=100.0)
    store.record(f"{ns}e1", f"{ns}new", mentioned_at=200.0)
    store.purge_older_than(150.0)
    assert store.list_for_elder(f"{ns}e1") == {f"{ns}new"}
