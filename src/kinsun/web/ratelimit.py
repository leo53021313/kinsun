"""認證端點滑動視窗節流（✅ D-58）：防登入／註冊暴力破解。

兩種實作：
- `SlidingWindowRateLimiter`：單進程記憶體版；測試與單 worker 部署可用。
- `PgRateLimiter`：以 Postgres 共享計數（✅ 庚-08／A-54），多 worker 下仍為
  全域上限——長輩帳號為低熵手機號，per-process 上限×worker 數會放大暴力破解面。

來源 IP 取 X-Forwarded-For 第一段——部署恆經 ngrok（會設此標頭）；直連僅限內網，
偽造標頭的風險接受。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Protocol

from fastapi import HTTPException, Request

from kinsun.db import Database

logger = logging.getLogger("kinsun.web.ratelimit")


class RateLimiter(Protocol):
    def hit(self, key: str) -> bool:
        """記錄一次嘗試並回傳是否放行；被擋的嘗試不計數（視窗過後即恢復）。"""
        ...


class SlidingWindowRateLimiter:
    """單進程記憶體實作；多 worker 下各進程獨立計數（實際上限＝設定值×worker 數）。"""

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
        """鍵數量上界＝出現過的來源 IP 數，此規模不做額外清理。"""
        now = self._clock()
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True


class PgRateLimiter:
    """Postgres 共享滑動視窗（✅ 庚-08）：多 worker 共用同一計數，全域上限精確。

    每次 hit 以 per-key 交易級 advisory lock 串行化「清舊→計數→寫入」，避免併發
    同鍵讀到過時計數而超額。時鐘用掛鐘（epoch 秒）以便跨進程可比。

    fail-open：節流僅為次級防線，且認證本身亦依賴 DB——節流查詢異常時放行並記警告，
    不讓節流表故障本身變成第二個服務中斷點（對齊本專案檢索 fail-open 哲學）。
    """

    def __init__(
        self,
        db: Database,
        max_attempts: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock

    def hit(self, key: str) -> bool:
        now = self._clock()
        cutoff = now - self._window
        try:
            with self._db.transaction() as tx:
                # hashtext 把字串鍵映成 int4 供 advisory lock；同鍵串行、不同鍵不互擋。
                tx.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
                tx.execute(
                    "DELETE FROM rate_limit_hits WHERE key = %s AND hit_at <= %s",
                    (key, cutoff),
                )
                row = tx.query_one("SELECT count(*) FROM rate_limit_hits WHERE key = %s", (key,))
                count = int(row[0]) if row else 0
                if count >= self._max:
                    return False
                tx.execute("INSERT INTO rate_limit_hits (key, hit_at) VALUES (%s, %s)", (key, now))
                return True
        except Exception:  # noqa: BLE001 - 節流故障不得反噬服務可用性（fail-open）
            logger.warning("節流查詢異常，本次放行 key=%s", key)
            return True


def client_ip(request: Request) -> str:
    """來源 IP：X-Forwarded-For 第一段（ngrok 轉發），否則直連位址。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def throttle_or_429(limiter: RateLimiter, scope: str, request: Request) -> None:
    """認證端點共用節流守門（✅ D-58）：scope 區分端點、各自計數，超限回 429。"""
    if not limiter.hit(f"{scope}:{client_ip(request)}"):
        raise HTTPException(status_code=429, detail="too_many_requests")
