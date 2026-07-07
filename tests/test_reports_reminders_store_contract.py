"""ReminderLogStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。

reminder_log_id 與 created_at 兩欄由各 adapter 自行產生（Pg 用 new_id／clock，
Fake 用索引虛構），故合約只斷言雙方都會產生的欄位：elder_id／kind／content。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.reports.reminders import FakeReminderLogStore, PgReminderLogStore

TPE = timezone(timedelta(hours=8))
FIXED = datetime(2026, 7, 10, 9, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}rl{i}" for i in count(1))
        return PgReminderLogStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED,
            new_id=lambda: next(ids),
        )
    return FakeReminderLogStore()


def test_record_then_list_returns_matching_log(store, ns):
    store.record(f"{ns}e1", "medication", "早上用藥：A")
    got = {(r.kind, r.content) for r in store.list_for_elder(f"{ns}e1")}
    assert ("medication", "早上用藥：A") in got


def test_list_is_filtered_to_the_given_elder(store, ns):
    store.record(f"{ns}e1", "medication", "給 e1 的")
    store.record(f"{ns}e2", "appointment", "給 e2 的")
    rows = store.list_for_elder(f"{ns}e1")
    assert all(r.elder_id == f"{ns}e1" for r in rows)
    contents = {r.content for r in rows}
    assert "給 e1 的" in contents
    assert "給 e2 的" not in contents


def test_multiple_records_for_same_elder_all_returned(store, ns):
    store.record(f"{ns}e1", "medication", "早上用藥：A")
    store.record(f"{ns}e1", "appointment", "明天回診：B")
    got = {(r.kind, r.content) for r in store.list_for_elder(f"{ns}e1")}
    assert ("medication", "早上用藥：A") in got
    assert ("appointment", "明天回診：B") in got
