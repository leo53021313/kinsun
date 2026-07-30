from datetime import datetime, timedelta, timezone

from kinsun.memory.shortterm import previous_day_bounds

TPE = timezone(timedelta(hours=8))


def test_previous_day_bounds_is_the_completed_day_before_now():
    # 凌晨 3 點跑的整理批次，要整理「剛結束的那一天」(6/28 整天)，
    # 而不是當下這天才過幾小時的片段 (6/29 00:00–03:00)。
    now = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    start, end = previous_day_bounds(now)
    assert start == datetime(2026, 6, 28, 0, 0, tzinfo=TPE).timestamp()
    assert end == datetime(2026, 6, 29, 0, 0, tzinfo=TPE).timestamp()


def test_previous_day_bounds_excludes_today_and_day_before_yesterday():
    now = datetime(2026, 6, 29, 23, 30, tzinfo=TPE)
    start, end = previous_day_bounds(now)
    # 6/27 23:59 不算進來，6/28 任意時刻算，6/29 00:00 起不算
    assert datetime(2026, 6, 27, 23, 59, tzinfo=TPE).timestamp() < start
    assert start <= datetime(2026, 6, 28, 9, 0, tzinfo=TPE).timestamp() < end
    assert end <= datetime(2026, 6, 29, 0, 0, tzinfo=TPE).timestamp()


# ── 併發輪的對話順序（spec 2026-07-28 P3）──────────────────────────────


def test_speak_time_keeps_concurrent_turns_in_the_order_the_elder_spoke():
    """⚠️ 併發輪的寫入時刻是「誰先算完誰先寫」，不是長輩開口的順序。

    情境：長輩先問新聞（要查工具、慢），三秒後又問天氣（快）。天氣先算完先寫，
    新聞後寫——若以寫入時刻排序，隔天 recall 讀到的對話順序是**顛倒的**，摘要
    也跟著錯。更糟的是兩輪的 user／assistant 可能交錯寫入，讀起來像被打散的對話。

    以長輩開口的時刻當排序鍵時，`created_at` 主導排序，兩個問題一起消失。
    """
    from kinsun.llm import Message
    from kinsun.memory.shortterm import FakeMemoryStore

    now = datetime(2026, 7, 28, 12, 0, tzinfo=TPE)
    store = FakeMemoryStore(now=now)
    spoke_news = now
    spoke_weather = now + timedelta(seconds=3)

    # 交錯寫入，且天氣（後問）整輪先完成——正是併發時真正會發生的順序。
    store.append("e1", Message("user", "今天有什麼新消息"), at=spoke_news)
    store.append("e1", Message("user", "那天氣呢"), at=spoke_weather)
    store.append("e1", Message("assistant", "今天三十二度"), at=spoke_weather)
    store.append("e1", Message("assistant", "今天有三則新聞"), at=spoke_news)

    assert [m.content for m in store.recent("e1")] == [
        "今天有什麼新消息",
        "今天有三則新聞",
        "那天氣呢",
        "今天三十二度",
    ]


def test_append_without_a_speak_time_keeps_the_previous_behaviour():
    """單輪路徑不傳 `at`＝沿用寫入當下，行為與本功能之前一字不差。"""
    from kinsun.llm import Message
    from kinsun.memory.shortterm import FakeMemoryStore

    now = datetime(2026, 7, 28, 12, 0, tzinfo=TPE)
    store = FakeMemoryStore(now=now)
    store.append("e1", Message("user", "阿公早安"))
    store.append("e1", Message("assistant", "早安喔"))
    assert [m.content for m in store.recent("e1")] == ["阿公早安", "早安喔"]


def test_recent_wrapped_with_span(monkeypatch):
    """今日對話查詢一顆 span（2026-07-30 spec）：memory_assemble 三段串行裡
    唯一沒露臉的一段。output 關（TurnContext.history 已含同一份內容）。"""
    import opik

    from kinsun.memory.shortterm import PgMemoryStore
    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    tracing_client.reset_for_test()
    seen: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (seen.append(kw), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)

    class _Db:
        def query(self, sql, params=()):
            return []

    store = PgMemoryStore(_Db(), clock=lambda: datetime(2026, 7, 30, 12, 0, tzinfo=TPE))
    assert store.recent("e1") == []
    spans = [kw for kw in seen if kw["name"] == "shortterm_recent"]
    assert spans and spans[0]["capture_output"] is False
