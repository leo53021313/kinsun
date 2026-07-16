"""MemoryStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。兩者以相同的固定時鐘與 max_turns
建構，斷言一律以 `ns` 前綴 scope 到本測試自己的 session，才能在共用真庫上互不干擾。

注意：Pg 的 append 一律以 clock 蓋時間戳、無法用參數回填過去，故 previous_day 只驗
「今日對話不落入前一天」這個兩邊都能透過公開介面設置的行為。要在特定時刻佈資料
請用 `append_at` 夾具——它把「Fake 用 at=、Pg 用可變時鐘」這唯一的差異收斂在一處。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kinsun.llm import Message
from kinsun.memory.shortterm import FakeMemoryStore, PgMemoryStore

_TPE = timezone(timedelta(hours=8))
_NOW = datetime(2026, 7, 4, 10, 0, tzinfo=_TPE)
_MAX_TURNS = 3


@pytest.fixture
def now_box() -> list[datetime]:
    """Pg 的可變時鐘：平時固定回 _NOW，只有 append_at 會短暫撥動它。"""
    return [_NOW]


@pytest.fixture(params=["fake", "pg"])
def store(request, now_box):
    if request.param == "pg":
        return PgMemoryStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: now_box[0],
            max_turns=_MAX_TURNS,
        )
    return FakeMemoryStore(now=_NOW, max_turns=_MAX_TURNS)


@pytest.fixture
def append_at(store, now_box):
    """在指定時刻寫入一輪對話——兩個 adapter 的差異只在這裡收斂，斷言得以完全共用。

    Fake 的 append 支援 at=；Pg 的 append 一律以 clock 蓋時間戳，故先把可變時鐘撥到
    該時刻再寫、寫完撥回 _NOW（其餘測試看到的時鐘與原本一模一樣）。兩者最終都讓
    turns.created_at 等於 at。
    """

    def _append(elder_id: str, message: Message, at: datetime) -> None:
        if isinstance(store, FakeMemoryStore):
            store.append(elder_id, message, at=at)
            return
        now_box[0] = at
        try:
            store.append(elder_id, message)
        finally:
            now_box[0] = _NOW

    return _append


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


def test_first_user_turn_per_day_returns_one_per_day(store, ns, append_at):
    """每天只回最早的那一則：一天講十次話，能說明她幾點起床的只有第一次。"""
    day1_early = datetime(2026, 7, 10, 9, 15, tzinfo=_TPE)
    day1_late = datetime(2026, 7, 10, 14, 0, tzinfo=_TPE)
    day2 = datetime(2026, 7, 11, 8, 30, tzinfo=_TPE)
    for at, text in ((day1_early, "早"), (day1_late, "午"), (day2, "隔天早")):
        append_at(f"{ns}e1", Message("user", text), at)

    since = datetime(2026, 7, 10, tzinfo=_TPE).timestamp()
    before = datetime(2026, 7, 12, tzinfo=_TPE).timestamp()
    got = store.first_user_turn_per_day(f"{ns}e1", since=since, before=before)

    assert got == [day1_early.timestamp(), day2.timestamp()]


def test_first_user_turn_per_day_ignores_assistant_turns(store, ns, append_at):
    """金孫自己的問候不算「她醒了」，否則訊號會被系統自己的排程時間污染。"""
    bot_first = datetime(2026, 7, 10, 8, 0, tzinfo=_TPE)
    user_later = datetime(2026, 7, 10, 10, 0, tzinfo=_TPE)
    append_at(f"{ns}e1", Message("assistant", "早安"), bot_first)
    append_at(f"{ns}e1", Message("user", "嗯"), user_later)

    since = datetime(2026, 7, 10, tzinfo=_TPE).timestamp()
    before = datetime(2026, 7, 11, tzinfo=_TPE).timestamp()
    got = store.first_user_turn_per_day(f"{ns}e1", since=since, before=before)

    assert got == [user_later.timestamp()]


def test_first_user_turn_per_day_is_empty_when_no_turns(store, ns):
    since = datetime(2026, 7, 10, tzinfo=_TPE).timestamp()
    before = datetime(2026, 7, 11, tzinfo=_TPE).timestamp()
    assert store.first_user_turn_per_day(f"{ns}silent", since=since, before=before) == []


def test_first_user_turn_per_day_excludes_turns_outside_the_window(store, ns, append_at):
    """窗界必須是 [since, before)：before 那一刻的發言屬於下一批，不得混入。

    夜間批次逐日推進，窗界若含右端點，同一則發言會被前後兩批各算一次。
    """
    before_window = datetime(2026, 7, 9, 23, 0, tzinfo=_TPE)
    at_since = datetime(2026, 7, 10, 0, 0, tzinfo=_TPE)
    at_before = datetime(2026, 7, 11, 0, 0, tzinfo=_TPE)
    for at in (before_window, at_since, at_before):
        append_at(f"{ns}e2", Message("user", "話"), at)

    got = store.first_user_turn_per_day(
        f"{ns}e2", since=at_since.timestamp(), before=at_before.timestamp()
    )

    assert got == [at_since.timestamp()]


def test_first_user_turn_per_day_is_not_capped_by_max_turns(store, ns, append_at):
    """訊號是統計量，不受聊天上下文的 max_turns（此處為 3）牽制。

    她一天可能講幾十輪；若讀取套上 max_turns，多數日子的「第一則」會被截掉，
    中位數就會被少數安靜的日子帶偏。
    """
    days = [datetime(2026, 7, 10 + i, 9, 0, tzinfo=_TPE) for i in range(5)]
    for day in days:
        append_at(f"{ns}e3", Message("user", "早"), day)
        append_at(f"{ns}e3", Message("user", "再一句"), day.replace(hour=20))

    got = store.first_user_turn_per_day(
        f"{ns}e3",
        since=datetime(2026, 7, 10, tzinfo=_TPE).timestamp(),
        before=datetime(2026, 7, 15, tzinfo=_TPE).timestamp(),
    )

    assert got == [d.timestamp() for d in days]
