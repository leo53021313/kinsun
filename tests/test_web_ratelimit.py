"""滑動視窗節流器（web/ratelimit.py）單元測試。"""

from kinsun.web.ratelimit import SlidingWindowRateLimiter


def _limiter(max_attempts=3, window_seconds=60.0, start=1000.0):
    state = {"now": start}
    limiter = SlidingWindowRateLimiter(max_attempts, window_seconds, clock=lambda: state["now"])
    return limiter, state


def test_allows_within_limit():
    limiter, _ = _limiter(max_attempts=3)
    assert all(limiter.hit("1.2.3.4") for _ in range(3))


def test_blocks_over_limit():
    limiter, _ = _limiter(max_attempts=3)
    for _ in range(3):
        limiter.hit("1.2.3.4")
    assert limiter.hit("1.2.3.4") is False


def test_keys_are_isolated():
    limiter, _ = _limiter(max_attempts=1)
    assert limiter.hit("1.2.3.4") is True
    assert limiter.hit("1.2.3.4") is False
    assert limiter.hit("5.6.7.8") is True


def test_window_slides_and_recovers():
    limiter, state = _limiter(max_attempts=2, window_seconds=60.0)
    limiter.hit("ip")
    limiter.hit("ip")
    assert limiter.hit("ip") is False
    state["now"] += 61.0
    assert limiter.hit("ip") is True


def test_blocked_attempt_does_not_extend_window():
    """被擋的嘗試不計入次數：視窗過後應立即恢復。"""
    limiter, state = _limiter(max_attempts=1, window_seconds=60.0)
    limiter.hit("ip")
    state["now"] += 30.0
    assert limiter.hit("ip") is False
    state["now"] += 31.0  # 第一次 hit 已滑出視窗
    assert limiter.hit("ip") is True
