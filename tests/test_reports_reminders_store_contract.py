"""ReminderLogStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。

reminder_log_id 由各 adapter 自行產生（Pg 用 new_id、Fake 用索引虛構），故合約不
斷言它。created_at 兩邊都走注入的時鐘，因回應時間窗的判定需要真實的時間語意；其餘
斷言集中在雙方都會產生的欄位：elder_id／kind／content／responded_at。

時鐘每被取用一次就前進一秒（每則 record 恰好取一次），故同一測試裡先後記下的提醒
不會撞秒——真實世界本來就不會，而 `mark_responded` 在撞秒時選中哪一則是未定義行為
（見 ReminderLogStore Protocol），Fake 與 Pg 對此不保證等價。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.reports.reminders import FakeReminderLogStore, PgReminderLogStore

TPE = timezone(timedelta(hours=8))
FIXED = datetime(2026, 7, 10, 9, tzinfo=TPE)


def _ticking_clock():
    """每次取用往前一秒：第一則 record 落在 FIXED，第 n 則落在 FIXED + (n-1) 秒。"""
    ticks = count()
    return lambda: FIXED + timedelta(seconds=next(ticks))


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}rl{i}" for i in count(1))
        return PgReminderLogStore(
            request.getfixturevalue("pg_database"),
            clock=_ticking_clock(),
            new_id=lambda: next(ids),
        )
    return FakeReminderLogStore(clock=_ticking_clock())


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


def test_mark_responded_flags_a_reminder_inside_the_window(store, ns):
    store.record(f"{ns}e1", "medication", "早上用藥：A")
    logged_at = FIXED.timestamp()

    store.mark_responded(f"{ns}e1", now=logged_at + 600, within_seconds=3600)

    rows = [r for r in store.list_for_elder(f"{ns}e1") if r.content == "早上用藥：A"]
    assert rows[0].responded_at is not None


def test_mark_responded_ignores_a_reminder_outside_the_window(store, ns):
    store.record(f"{ns}e1", "medication", "太久以前的提醒")
    logged_at = FIXED.timestamp()

    store.mark_responded(f"{ns}e1", now=logged_at + 7200, within_seconds=3600)

    rows = [r for r in store.list_for_elder(f"{ns}e1") if r.content == "太久以前的提醒"]
    assert rows[0].responded_at is None


def test_mark_responded_does_not_chain_to_older_reminders(store, ns):
    """連續發言不得往回啃更舊的提醒（回歸測試：串連標記會把回應率灌到近 100%）。"""
    store.record(f"{ns}e1", "medication", "早上用藥：A")
    store.record(f"{ns}e1", "proactive-greeting", "阿嬤早安")
    at = FIXED.timestamp()

    store.mark_responded(f"{ns}e1", now=at + 600, within_seconds=3600)
    store.mark_responded(f"{ns}e1", now=at + 900, within_seconds=3600)

    rows = {r.content: r for r in store.list_for_elder(f"{ns}e1")}
    # 第二次發言重新選中同一則（已標記）→ no-op：既不覆寫首次回應時間，也不往下啃。
    assert rows["阿嬤早安"].responded_at == at + 600
    assert rows["早上用藥：A"].responded_at is None


def test_list_for_range_returns_only_reminders_inside_the_bounds(store, ns):
    store.record(f"{ns}e1", "medication", "區間內")
    at = FIXED.timestamp()

    inside = store.list_for_range(f"{ns}e1", start=at - 1, end=at + 1)
    outside = store.list_for_range(f"{ns}e1", start=at + 10, end=at + 20)

    assert "區間內" in {r.content for r in inside}
    assert "區間內" not in {r.content for r in outside}
