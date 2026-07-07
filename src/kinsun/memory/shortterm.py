"""短期記憶（今日對話上下文）：以 Postgres（Supabase）持久化每輪對話。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.llm import Message


class MemoryError(Exception):
    """短期記憶讀寫失敗。"""


def previous_day_bounds(now: datetime) -> tuple[float, float]:
    """回傳『剛結束的那一天』的 [起, 迄) Unix 時間戳（沿用 now 的時區）。

    供夜間整理批次使用：例如凌晨 3 點執行時，要整理前一天整天的對話，
    而不是當下這天才過幾小時的片段。
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_start = today_start - timedelta(days=1)
    return prev_start.timestamp(), today_start.timestamp()


class MemoryStore(Protocol):
    def append(self, elder_id: str, message: Message) -> None: ...
    def recent(self, elder_id: str) -> list[Message]: ...
    def previous_day(self, elder_id: str) -> list[Message]: ...
    def sessions(self) -> list[str]: ...
    def last_active(self, elder_id: str) -> float | None: ...


class PgMemoryStore:
    """短期記憶的 Postgres（Supabase）實作；介面同 MemoryStore。"""

    def __init__(self, db: Database, clock: Callable[[], datetime], max_turns: int = 20) -> None:
        self._db = _Errors(db, lambda m: MemoryError(f"記憶存取失敗：{m}"))
        self._clock = clock
        self._max_turns = max_turns

    def append(self, elder_id: str, message: Message) -> None:
        created_at = self._clock().timestamp()
        self._db.execute(
            "INSERT INTO turns (elder_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
            (elder_id, message.role, message.content, created_at),
        )

    def recent(self, elder_id: str) -> list[Message]:
        start = self._start_of_today()
        rows = self._db.query(
            "SELECT role, content FROM turns WHERE elder_id = %s AND created_at >= %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (elder_id, start, self._max_turns),
        )
        return [Message(role=r, content=t) for r, t in reversed(rows)]

    def previous_day(self, elder_id: str) -> list[Message]:
        """整理批次用：回傳『剛結束的那一天』整天的對話（時序由舊到新）。"""
        start, end = previous_day_bounds(self._clock())
        rows = self._db.query(
            "SELECT role, content FROM turns "
            "WHERE elder_id = %s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at ASC, id ASC LIMIT %s",
            (elder_id, start, end, self._max_turns),
        )
        return [Message(role=r, content=t) for r, t in rows]

    def sessions(self) -> list[str]:
        rows = self._db.query(
            "SELECT DISTINCT elder_id FROM turns WHERE elder_id IS NOT NULL ORDER BY elder_id"
        )
        return [r[0] for r in rows]

    def last_active(self, elder_id: str) -> float | None:
        row = self._db.query_one(
            "SELECT MAX(created_at) FROM turns WHERE elder_id = %s AND role = 'user'",
            (elder_id,),
        )
        return row[0] if row and row[0] is not None else None

    def _start_of_today(self) -> float:
        now = self._clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()


_FAKE_DEFAULT_NOW = datetime(2026, 6, 29, 3, 0, tzinfo=timezone(timedelta(hours=8)))


class FakeMemoryStore:
    """MemoryStore 的記憶體替身（測試用，不碰 DB）。

    忠實複製 Pg 的 max_turns 上限與時序（依 created_at、再依寫入序）：
    recent 回「今日最近 N 輪、由舊到新」，previous_day 回「前一天前 N 輪、由舊到新」。
    """

    def __init__(self, now: datetime | None = None, max_turns: int = 20) -> None:
        self._now = now or _FAKE_DEFAULT_NOW
        self._max_turns = max_turns
        self._turns: dict[str, list[tuple[float, Message]]] = {}

    def append(self, elder_id: str, message: Message, *, at: datetime | None = None) -> None:
        ts = (at or self._now).timestamp()
        self._turns.setdefault(elder_id, []).append((ts, message))

    def recent(self, elder_id: str) -> list[Message]:
        midnight = self._now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        rows = sorted(
            (
                (ts, i, m)
                for i, (ts, m) in enumerate(self._turns.get(elder_id, []))
                if ts >= midnight
            ),
            key=lambda r: (r[0], r[1]),
        )
        return [m for _, _, m in rows[-self._max_turns :]]

    def previous_day(self, elder_id: str) -> list[Message]:
        start, end = previous_day_bounds(self._now)
        rows = sorted(
            (
                (ts, i, m)
                for i, (ts, m) in enumerate(self._turns.get(elder_id, []))
                if start <= ts < end
            ),
            key=lambda r: (r[0], r[1]),
        )
        return [m for _, _, m in rows[: self._max_turns]]

    def sessions(self) -> list[str]:
        return sorted(self._turns)

    def last_active(self, elder_id: str) -> float | None:
        users = [ts for ts, m in self._turns.get(elder_id, []) if m.role == "user"]
        return max(users) if users else None
