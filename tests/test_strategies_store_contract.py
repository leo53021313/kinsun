"""StrategyStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。

strategy_id 與 created_at 兩欄由各 adapter 自行產生（Pg 用 new_id／clock，
Fake 用索引虛構），故合約只斷言雙方都會產生的欄位。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.strategies.models import (
    STRATEGY_CATEGORY_ROUTINE,
    STRATEGY_CATEGORY_TONE,
    STRATEGY_STATUS_ADOPTED,
    STRATEGY_STATUS_REVOKED,
    STRATEGY_STATUS_SUPERSEDED,
)
from kinsun.strategies.store import FakeStrategyStore, PgStrategyStore, StrategyError

TPE = timezone(timedelta(hours=8))
FIXED = datetime(2026, 7, 14, 3, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}st{i}" for i in count(1))
        return PgStrategyStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED,
            new_id=lambda: next(ids),
        )
    # Pg 的 clock 回 datetime、Fake 回 epoch 秒（沿用 FakeRiskEventStore 前例），
    # 兩者餵同一個時刻，revoked_at 才能在合約裡對同一個值斷言。
    return FakeStrategyStore(clock=lambda: FIXED.timestamp())


def test_record_writes_an_adopted_strategy(store, ns):
    store.record(
        f"{ns}e1", "早上七點半再問候", STRATEGY_CATEGORY_ROUTINE, "連三天八點沒回", 3, None
    )
    rows = store.list_for_elder(f"{ns}e1")
    assert [(r.content, r.category, r.observed_days, r.status) for r in rows] == [
        ("早上七點半再問候", STRATEGY_CATEGORY_ROUTINE, 3, STRATEGY_STATUS_ADOPTED)
    ]


def test_list_for_elder_can_filter_by_status(store, ns):
    store.record(f"{ns}e1", "回話簡短些", STRATEGY_CATEGORY_TONE, "長句多半沒回", 4, None)
    adopted = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)
    assert [r.content for r in adopted] == ["回話簡短些"]
    assert store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_REVOKED) == []


def test_list_is_scoped_to_the_given_elder(store, ns):
    store.record(f"{ns}e1", "給 e1 的", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    store.record(f"{ns}e2", "給 e2 的", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    contents = {r.content for r in store.list_for_elder(f"{ns}e1")}
    assert "給 e1 的" in contents
    assert "給 e2 的" not in contents


def test_list_for_status_spans_elders(store, ns):
    store.record(f"{ns}e1", "e1 的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    store.record(f"{ns}e2", "e2 的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    contents = {r.content for r in store.list_for_status(STRATEGY_STATUS_ADOPTED)}
    assert {"e1 的守則", "e2 的守則"} <= contents


def test_record_with_supersedes_retires_the_old_one_atomically(store, ns):
    store.record(f"{ns}e1", "舊守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    old = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)[0]

    store.record(f"{ns}e1", "新守則", STRATEGY_CATEGORY_TONE, "更新的證據", 5, old.strategy_id)

    adopted = {r.content for r in store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)}
    superseded = {
        r.content for r in store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_SUPERSEDED)
    }
    assert adopted == {"新守則"}
    assert superseded == {"舊守則"}


def test_revoke_takes_a_strategy_out_of_effect(store, ns):
    store.record(f"{ns}e1", "要撤掉的", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    target = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)[0]

    store.revoke(target.strategy_id)

    assert store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED) == []
    revoked = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_REVOKED)
    assert [r.content for r in revoked] == ["要撤掉的"]


def test_revoke_stamps_revoked_at_from_the_clock(store, ns):
    store.record(f"{ns}e1", "要撤掉的", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    target = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)[0]

    store.revoke(target.strategy_id)

    revoked = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_REVOKED)[0]
    assert revoked.revoked_at == FIXED.timestamp()


def test_revoking_an_unknown_strategy_id_is_a_silent_no_op(store, ns):
    """釘住現況：撤銷不存在的守則不報錯、也不憑空生出任何列。

    revoke 的唯一呼叫端是後台人工操作，找不到就是沒事發生；此處只固定行為，
    不主張它是唯一正解。
    """
    store.revoke(f"{ns}nonexistent")

    assert store.list_for_elder(f"{ns}e1") == []


def test_record_rejects_superseding_a_revoked_strategy(store, ns):
    """人工撤銷過的守則不得被當成取代對象——否則等於讓它借屍還魂、且鑿穿上限。"""
    store.record(f"{ns}e1", "被撤銷的", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    target = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)[0]
    store.revoke(target.strategy_id)

    with pytest.raises(StrategyError):
        store.record(
            f"{ns}e1", "近似的新守則", STRATEGY_CATEGORY_TONE, "新證據", 5, target.strategy_id
        )

    assert store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED) == []
    revoked = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_REVOKED)
    assert [r.content for r in revoked] == ["被撤銷的"]


def test_record_rejects_superseding_another_elders_strategy(store, ns):
    store.record(f"{ns}e1", "e1 的守則", STRATEGY_CATEGORY_TONE, "證據", 3, None)
    target = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)[0]

    with pytest.raises(StrategyError):
        store.record(f"{ns}e2", "越界取代", STRATEGY_CATEGORY_TONE, "證據", 3, target.strategy_id)

    assert store.list_for_elder(f"{ns}e2") == []
    still_adopted = store.list_for_elder(f"{ns}e1", status=STRATEGY_STATUS_ADOPTED)
    assert [r.content for r in still_adopted] == ["e1 的守則"]


def test_record_rejects_a_category_outside_the_whitelist(store, ns):
    """縱深防禦：白名單在持久層也要擋，旁路寫入端才無法塞進 medication 類守則。"""
    with pytest.raises(StrategyError):
        store.record(f"{ns}e1", "把血壓藥加倍", "medication", "證據", 3, None)

    assert store.list_for_elder(f"{ns}e1") == []
