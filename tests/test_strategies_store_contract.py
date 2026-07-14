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
from kinsun.strategies.store import FakeStrategyStore, PgStrategyStore

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
    return FakeStrategyStore()


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
