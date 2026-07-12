"""PgRateLimiter 整合測試（✅ 庚-08）：多 worker 共用同一 DB 計數的關鍵性質。

需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`（連獨立測試庫）。離線 skip。
"""

from __future__ import annotations

from kinsun.web.ratelimit import PgRateLimiter


def _clock():
    state = {"now": 1000.0}
    return state, lambda: state["now"]


def test_count_is_shared_across_limiter_instances(pg_database, ns):
    """兩個 PgRateLimiter 實例（模擬兩個 worker）共用同一 DB → 上限為全域，不隨實例數放大。"""
    state, clock = _clock()
    worker1 = PgRateLimiter(pg_database, 3, 60.0, clock=clock)
    worker2 = PgRateLimiter(pg_database, 3, 60.0, clock=clock)
    key = f"login:{ns}1.2.3.4"
    # 三次嘗試分散到兩個 worker，都在同一視窗內。
    assert worker1.hit(key) is True
    assert worker2.hit(key) is True
    assert worker1.hit(key) is True
    # 第 4 次不論打到哪個 worker 都應被擋——計數是共享的（庚-08 的核心修復）。
    assert worker2.hit(key) is False
    assert worker1.hit(key) is False


def test_window_slides_and_recovers(pg_database, ns):
    state, clock = _clock()
    limiter = PgRateLimiter(pg_database, 2, 60.0, clock=clock)
    key = f"login:{ns}5.6.7.8"
    assert limiter.hit(key) is True
    assert limiter.hit(key) is True
    assert limiter.hit(key) is False
    state["now"] += 61.0  # 兩筆皆滑出視窗
    assert limiter.hit(key) is True


def test_keys_are_isolated(pg_database, ns):
    state, clock = _clock()
    limiter = PgRateLimiter(pg_database, 1, 60.0, clock=clock)
    assert limiter.hit(f"login:{ns}a") is True
    assert limiter.hit(f"login:{ns}a") is False
    assert limiter.hit(f"register:{ns}a") is True  # 不同 scope 獨立計數
    assert limiter.hit(f"login:{ns}b") is True  # 不同 IP 獨立計數
