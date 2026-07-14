"""MemoryStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。兩者以相同的固定時鐘與 max_turns
建構，斷言一律以 `ns` 前綴 scope 到本測試自己的 session，才能在共用真庫上互不干擾。

注意：Pg 的 append 一律以 clock 蓋時間戳、無法回填過去，故 previous_day 只驗
「今日對話不落入前一天」這個兩邊都能透過公開介面設置的行為。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kinsun.llm import Message
from kinsun.memory.shortterm import FakeMemoryStore, PgMemoryStore

_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 7, 4, 10, 0, tzinfo=_TPE)
_MAX_TURNS = 3


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgMemoryStore(
            request.getfixturevalue("pg_database"), clock=lambda: _NOW, max_turns=_MAX_TURNS
        )
    return FakeMemoryStore(now=_NOW, max_turns=_MAX_TURNS)


def test_recent_returns_todays_turns_in_order(store, ns):
    sid = f"{ns}s1"
    store.append(sid, Message("user", "早安"))
    store.append(sid, Message("assistant", "阿公早"))
    assert [(m.role, m.content) for m in store.recent(sid)] == [
        ("user", "早安"),
        ("assistant", "阿公早"),
    ]


def test_recent_caps_at_max_turns_keeping_latest(store, ns):
    sid = f"{ns}s2"
    for i in range(5):
        store.append(sid, Message("user", f"m{i}"))
    got = [m.content for m in store.recent(sid)]
    assert got == ["m2", "m3", "m4"]  # 只留最近 max_turns（3）輪，且由舊到新


def test_previous_day_excludes_todays_turns(store, ns):
    sid = f"{ns}s3"
    store.append(sid, Message("user", "今天說的"))
    assert store.previous_day(sid) == []


def test_list_recent_in_range_caps_at_the_limit_keeping_the_latest(store, ns):
    """超過 limit 時保留的必須是**最新的**幾輪，不是最舊的。

    這是 `list_recent_in_range` 存在的唯一理由：`list_for_range` 的
    `ORDER BY ... ASC LIMIT n` 截掉的是最新的那幾天，反思跨七天讀時會讀到一片舊資料。
    """
    sid = f"{ns}s6"
    for i in range(5):
        store.append(sid, Message("user", f"m{i}"))
    got = store.list_recent_in_range(
        sid, start=_NOW.timestamp() - 1, end=_NOW.timestamp() + 1, limit=3
    )
    assert [m.content for m in got] == ["m2", "m3", "m4"]  # 最新三輪，但仍由舊到新排列


def test_list_recent_in_range_is_not_capped_by_max_turns(store, ns):
    """limit 由呼叫端決定，不受建構時的 max_turns（此處為 3）牽制。

    反思要看七天、上限是 REFLECTION_MAX_TURNS；聊天上下文要看今天、上限是
    MEMORY_MAX_TURNS。兩者是不同的窗，共用一個上限就是 C1 的病灶。
    """
    sid = f"{ns}s7"
    for i in range(5):
        store.append(sid, Message("user", f"m{i}"))
    got = store.list_recent_in_range(
        sid, start=_NOW.timestamp() - 1, end=_NOW.timestamp() + 1, limit=10
    )
    assert [m.content for m in got] == ["m0", "m1", "m2", "m3", "m4"]


def test_list_recent_in_range_excludes_turns_outside_the_window(store, ns):
    sid = f"{ns}s8"
    store.append(sid, Message("user", "窗內講的"))
    later = _NOW.timestamp() + 60
    assert store.list_recent_in_range(sid, start=later, end=later + 60, limit=10) == []


def test_sessions_lists_active_session(store, ns):
    sid = f"{ns}s4"
    store.append(sid, Message("user", "哈囉"))
    assert sid in store.sessions()


def test_last_active_is_none_without_user_turn(store, ns):
    sid_user = f"{ns}s5u"
    sid_assistant = f"{ns}s5a"
    store.append(sid_user, Message("user", "你好"))
    store.append(sid_assistant, Message("assistant", "您好"))
    assert store.last_active(sid_user) == _NOW.timestamp()
    assert store.last_active(sid_assistant) is None
