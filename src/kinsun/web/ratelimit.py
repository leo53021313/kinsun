"""per-IP 滑動視窗節流（✅ D-58）：防登入／註冊暴力破解。

單進程記憶體版：多 worker（丙-3）下各進程獨立計數，實際上限＝設定值×worker 數，
此規模可接受。來源 IP 取 X-Forwarded-For 第一段——部署恆經 ngrok（會設此標頭）；
直連僅限內網，偽造標頭的風險接受。
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from fastapi import Request


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """記錄一次嘗試並回傳是否放行；被擋的嘗試不計數（視窗過後即恢復）。

        鍵數量上界＝出現過的來源 IP 數，此規模不做額外清理。
        """
        now = self._clock()
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True


def client_ip(request: Request) -> str:
    """來源 IP：X-Forwarded-For 第一段（ngrok 轉發），否則直連位址。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
