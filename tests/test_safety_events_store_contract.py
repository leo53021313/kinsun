"""RiskEventStore 合約：Fake 與 Pg 兩個 adapter 對同一情境須給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。

漂移（drift）備註：這是 append/record 型 store，公開合約僅有 record 與
list_for_elder。兩個 adapter 皆「可靠產出」的欄位只有 elder_id、tier、
reason；risk_event_id 與 created_at 在 Fake 為合成值（依記錄序號），與 Pg 的
真實 UUID／時鐘時間不同，故不斷言。trace_id 兩者皆接受並保存，但 RiskEvent
無此欄位、Pg 的 SELECT 亦未取該欄，故無法經 list_for_elder 讀回——合約僅
斷言「帶或不帶 trace_id 都能記錄且可查回」，不斷言 trace_id 值本身。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.safety.events import FakeRiskEventStore, PgRiskEventStore
from kinsun.safety.tiers import RiskAssessment, RiskTier

TPE = timezone(timedelta(hours=8))
FIXED_CLOCK = datetime(2026, 7, 4, 9, 0, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}re{i}" for i in count(1))
        return PgRiskEventStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED_CLOCK,
            new_id=lambda: next(ids),
        )
    return FakeRiskEventStore(clock=lambda: FIXED_CLOCK.timestamp())


def test_record_then_list_returns_matching_tier_and_reason(store, ns):
    elder_id = f"{ns}U1"
    store.record(elder_id, RiskAssessment(RiskTier.L2, 0.9, "胸痛"))
    got = [e for e in store.list_for_elder(elder_id) if e.reason == "胸痛"]
    assert len(got) == 1
    assert got[0].tier == RiskTier.L2
    assert got[0].elder_id == elder_id


def test_list_is_scoped_to_line_user(store, ns):
    elder_id_1 = f"{ns}U1"
    elder_id_2 = f"{ns}U2"
    store.record(elder_id_1, RiskAssessment(RiskTier.L2, 0.9, "頭暈"))
    store.record(elder_id_2, RiskAssessment(RiskTier.L2, 0.95, "昏倒"))
    reasons = {e.reason for e in store.list_for_elder(elder_id_1)}
    assert "頭暈" in reasons
    assert "昏倒" not in reasons


def test_count_failsafe_since_counts_only_failsafe_in_window(store, ns):
    """✅ D-31（甲-5）：fail-safe 留痕事件可依時間窗計數，供 admin 告警門檻判斷。

    兩個 adapter 用同一固定時鐘：cutoff 在時鐘之前 → 數得到；之後 → 數不到。
    一般事件（reason 非 fail-safe 常數）不列入。
    """
    from kinsun.safety.tiers import FAILSAFE_EVENT_REASON

    elder_id = f"{ns}U1"
    store.record(elder_id, RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON))
    store.record(elder_id, RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON))
    store.record(elder_id, RiskAssessment(RiskTier.L2, 0.9, "頭暈"))
    ts = FIXED_CLOCK.timestamp()
    assert store.count_failsafe_since(ts - 1) >= 2  # 共用真庫可能有他組殘留，用下界斷言
    assert store.count_failsafe_since(ts + 1) == 0


def test_record_accepts_trace_id_and_event_stays_retrievable(store, ns):
    # trace_id 兩個 adapter 皆接受並保存，但不經 list_for_elder 對外揭露，
    # 故僅驗證「帶與不帶 trace_id 都能記錄且可查回」，不斷言 trace_id 值。
    elder_id = f"{ns}U1"
    store.record(elder_id, RiskAssessment(RiskTier.L2, 0.9, "帶追蹤"), trace_id=f"{ns}t1")
    store.record(elder_id, RiskAssessment(RiskTier.L1, 0.5, "不帶追蹤"))
    reasons = {e.reason for e in store.list_for_elder(elder_id)}
    assert reasons == {"帶追蹤", "不帶追蹤"}
