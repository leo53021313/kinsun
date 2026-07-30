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


def test_record_channels_roundtrip(store, ns):
    """✅ 庚-16（A-41）：實際走的通道隨留痕保存——admin 據此區分「真送達」與「入匣待拉取」。"""
    store.record(f"{ns}e9", f"{ns}g1", RiskTier.L2, delivered=True, channels="app")
    got = store.list_for_elder(f"{ns}e9")
    assert got[0].channels == "app"


def test_record_outcome_roundtrip(store, ns):
    """2026-07-27：outcome 記「為什麼沒送到」，Fake 與 Pg 必須同樣保存。"""
    store.record(f"{ns}e8", f"{ns}g1", RiskTier.L2, delivered=False, outcome="no_route")
    assert store.list_for_elder(f"{ns}e8")[0].outcome == "no_route"


def test_unrecorded_outcome_defaults_to_empty(store, ns):
    """舊資料與未指定 outcome 的呼叫端一律得到空字串（未分類），兩個實作一致。"""
    store.record(f"{ns}e7", f"{ns}g1", RiskTier.L2, delivered=True)
    assert store.list_for_elder(f"{ns}e7")[0].outcome == ""


def test_count_failed_since_excludes_guardians_with_no_route(store, ns):
    """未綁通道是常態不是故障，不可算進投遞失敗告警（2026-07-27）。

    未分類的舊資料（outcome=''）仍算失敗——寧可多報，不可讓歷史失敗憑空消失。
    """
    ts = FIXED_CLOCK.timestamp()
    before = store.count_failed_since(ts - 1)
    store.record(f"{ns}e3", f"{ns}g1", RiskTier.L2, delivered=False, outcome="no_route")
    assert store.count_failed_since(ts - 1) == before  # 沒有增加
    store.record(f"{ns}e3", f"{ns}g2", RiskTier.L2, delivered=False, outcome="failed")
    store.record(f"{ns}e3", f"{ns}g3", RiskTier.L2, delivered=False)  # 舊形狀＝未分類
    assert store.count_failed_since(ts - 1) == before + 2


def test_count_failed_since_counts_undelivered_across_elders(store, ns):
    """✅ 庚-02（A-40）：送達失敗（delivered=False）跨長輩全域計數，供 admin 告警。

    計數刻意不分長輩（admin 告警看全站），共用測試庫會累積他測資料，
    故以「記錄前後差值」斷言而非絕對值。
    """
    ts = FIXED_CLOCK.timestamp()
    before = store.count_failed_since(ts - 1)
    store.record(f"{ns}e1", f"{ns}g1", RiskTier.L2, delivered=True)
    store.record(f"{ns}e1", f"{ns}g2", RiskTier.L2, delivered=False)
    store.record(f"{ns}e2", f"{ns}g3", RiskTier.L2, delivered=False)
    assert store.count_failed_since(ts - 1) == before + 2  # 兩筆失敗（跨長輩），成功不計
    assert store.count_failed_since(ts + 1) == 0  # 視窗之後無（全部記錄都落在 ts）
