"""ConsolidationLogStore 合約：Fake 與 Pg 對同一情境須給出相同結果（✅ 庚-06／庚-13）。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`。斷言以 `ns` 前綴 scope。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kinsun.memory.longterm.consolidation_log import (
    FakeConsolidationLogStore,
    PgConsolidationLogStore,
)

TPE = timezone(timedelta(hours=8))
FIXED_CLOCK = datetime(2026, 7, 9, 9, 0, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgConsolidationLogStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED_CLOCK,
        )
    return FakeConsolidationLogStore()


def test_record_then_consolidated_days_scoped_to_elder(store, ns):
    store.record(f"{ns}e1", "2026-06-26", turn_count=3)
    store.record(f"{ns}e1", "2026-06-27", turn_count=5)
    store.record(f"{ns}e2", "2026-06-26", turn_count=1)
    assert store.consolidated_days(f"{ns}e1") == {"2026-06-26", "2026-06-27"}
    assert store.consolidated_days(f"{ns}e2") == {"2026-06-26"}


def test_record_is_idempotent_on_conflict(store, ns):
    """庚-13：同 (elder, day) 重覆標記為 no-op，不報錯、集合不變。"""
    store.record(f"{ns}e1", "2026-06-28", turn_count=2)
    store.record(f"{ns}e1", "2026-06-28", turn_count=9)  # 重覆 → DO NOTHING
    assert store.consolidated_days(f"{ns}e1") == {"2026-06-28"}


def test_consolidated_days_empty_for_unknown_elder(store, ns):
    assert store.consolidated_days(f"{ns}nobody") == set()
