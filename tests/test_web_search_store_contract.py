"""WebSearchLookupStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連獨立測試庫）。斷言以 `ns` 前綴 scope 到本測試
自己的 query，才能在共用測試庫上互不干擾。
"""

from __future__ import annotations

import itertools
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kinsun.tools.lookups import (
    STATUS_EMPTY,
    STATUS_OK,
    FakeWebSearchLookupStore,
    PgWebSearchLookupStore,
)

_SOURCES = [{"title": "颱風假公告", "site": "cdc.gov.tw", "url": "https://cdc.gov.tw/a"}]


def _counter_clock():
    """單調遞增時鐘：讓 Pg 的 created_at 排序可預期，對齊 Fake 的附加順序。"""
    ticks = itertools.count(1)
    return lambda: datetime.fromtimestamp(next(ticks), tz=ZoneInfo("Asia/Taipei"))


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        ids = itertools.count(1)
        return PgWebSearchLookupStore(
            request.getfixturevalue("pg_database"),
            clock=_counter_clock(),
            new_id=lambda: f"wsl-{next(ids)}-{request.node.name}",
        )
    return FakeWebSearchLookupStore()


def _mine(store, ns):
    return [lookup for lookup in store.list_recent(limit=50) if lookup.query.startswith(ns)]


def test_list_recent_empty_before_record(store, ns):
    assert _mine(store, ns) == []


def test_record_then_list_round_trips(store, ns):
    store.record(query=f"{ns}颱風假", topic="general", status=STATUS_OK, sources=_SOURCES)
    got = _mine(store, ns)
    assert len(got) == 1
    assert got[0].query == f"{ns}颱風假"
    assert got[0].topic == "general"
    assert got[0].status == STATUS_OK
    assert got[0].sources == _SOURCES


def test_record_empty_sources_round_trips(store, ns):
    store.record(query=f"{ns}查無", topic="rumor_check", status=STATUS_EMPTY, sources=[])
    got = _mine(store, ns)
    assert len(got) == 1
    assert got[0].status == STATUS_EMPTY
    assert got[0].sources == []


def test_list_recent_orders_newest_first(store, ns):
    store.record(query=f"{ns}舊", topic="general", status=STATUS_OK, sources=[])
    store.record(query=f"{ns}新", topic="general", status=STATUS_OK, sources=[])
    assert [lookup.query for lookup in _mine(store, ns)] == [f"{ns}新", f"{ns}舊"]
