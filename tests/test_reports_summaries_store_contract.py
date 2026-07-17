"""ConversationSummaryStore 合約：Fake 與 Pg 兩個 adapter 對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到本
測試自己的資料；list_for_elder 本就以 elder_id 收斂，故可對「本人的列」
做完整相等斷言而互不干擾。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kinsun.reports.summaries import (
    FakeConversationSummaryStore,
    PgConversationSummaryStore,
)

FIXED = datetime(2026, 7, 11, 3, 0, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgConversationSummaryStore(
            request.getfixturevalue("pg_database"), clock=lambda: FIXED
        )
    return FakeConversationSummaryStore()


def test_save_then_list_returns_content(store, ns):
    store.save(f"{ns}u1", "2026-07-10", "阿公今天心情不錯")
    rows = store.list_for_elder(f"{ns}u1")
    assert [(r.date, r.content) for r in rows] == [("2026-07-10", "阿公今天心情不錯")]


def test_save_same_date_upserts(store, ns):
    store.save(f"{ns}u1", "2026-07-10", "舊摘要")
    store.save(f"{ns}u1", "2026-07-10", "新摘要")  # 同 (line_user_id, date) 覆蓋
    rows = store.list_for_elder(f"{ns}u1")
    assert len(rows) == 1
    assert rows[0].content == "新摘要"


def test_list_is_newest_date_first(store, ns):
    # 存入順序刻意與日期相反，證明回傳依 date 由新到舊而非依存入順序。
    store.save(f"{ns}u1", "2026-07-10", "十號")
    store.save(f"{ns}u1", "2026-07-12", "十二號")
    store.save(f"{ns}u1", "2026-07-11", "十一號")
    assert [r.date for r in store.list_for_elder(f"{ns}u1")] == [
        "2026-07-12",
        "2026-07-11",
        "2026-07-10",
    ]


def test_get_for_date_returns_that_days_summary(store, ns):
    store.save(f"{ns}u1", "2026-07-10", "十號")
    store.save(f"{ns}u1", "2026-07-11", "十一號")
    row = store.get_for_date(f"{ns}u1", "2026-07-10")
    assert row is not None
    assert (row.date, row.content) == ("2026-07-10", "十號")


def test_get_for_date_returns_none_when_that_day_has_none(store, ns):
    # 那天沒講話 → summarize_day 不存列 → 主動問候據此退回無脈絡行為。
    store.save(f"{ns}u1", "2026-07-10", "十號")
    assert store.get_for_date(f"{ns}u1", "2026-07-09") is None


def test_get_for_date_is_scoped_to_elder(store, ns):
    store.save(f"{ns}u2", "2026-07-10", "u2 的摘要")
    assert store.get_for_date(f"{ns}u1", "2026-07-10") is None


def test_list_is_scoped_to_line_user(store, ns):
    store.save(f"{ns}u1", "2026-07-10", "u1 的摘要")
    store.save(f"{ns}u2", "2026-07-10", "u2 的摘要")
    rows = store.list_for_elder(f"{ns}u1")
    assert [(r.date, r.content) for r in rows] == [("2026-07-10", "u1 的摘要")]
