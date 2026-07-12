"""RiskNotificationLogStore 合約：Fake 與 Pg 對同一情境須給出相同結果（✅ D-36 丙-7）。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`。斷言以 `ns`
前綴 scope；id 與 created_at 在 Fake 為合成值，不斷言。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.safety.deliveries import FakeRiskNotificationLogStore, PgRiskNotificationLogStore
from kinsun.safety.tiers import RiskTier

TPE = timezone(timedelta(hours=8))
FIXED_CLOCK = datetime(2026, 7, 9, 9, 0, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}nl{i}" for i in count(1))
        return PgRiskNotificationLogStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED_CLOCK,
            new_id=lambda: next(ids),
        )
    return FakeRiskNotificationLogStore(clock=lambda: FIXED_CLOCK.timestamp())


def test_record_then_list_scoped_to_elder(store, ns):
    store.record(f"{ns}e1", f"{ns}g1", RiskTier.L2, delivered=True)
    store.record(f"{ns}e1", f"{ns}g2", RiskTier.L2, delivered=False)
    store.record(f"{ns}e2", f"{ns}g1", RiskTier.L2, delivered=True)
    got = store.list_for_elder(f"{ns}e1")
    assert {(d.guardian_id, d.delivered) for d in got} == {
        (f"{ns}g1", True),
        (f"{ns}g2", False),
    }
    assert all(d.tier == RiskTier.L2 for d in got)


def test_count_failed_since_counts_undelivered_across_elders(store, ns):
    """✅ 庚-02（A-40）：送達失敗（delivered=False）跨長輩全域計數，供 admin 告警。"""
    store.record(f"{ns}e1", f"{ns}g1", RiskTier.L2, delivered=True)
    store.record(f"{ns}e1", f"{ns}g2", RiskTier.L2, delivered=False)
    store.record(f"{ns}e2", f"{ns}g3", RiskTier.L2, delivered=False)
    ts = FIXED_CLOCK.timestamp()
    assert store.count_failed_since(ts - 1) == 2  # 兩筆失敗（跨長輩），成功不計
    assert store.count_failed_since(ts + 1) == 0  # 視窗之後無
