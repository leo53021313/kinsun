"""短期記憶（今日對話上下文）：以 Postgres（Supabase）持久化每輪對話。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
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
    def append(self, line_user_id: str, message: Message) -> None: ...
    def recent(self, line_user_id: str) -> list[Message]: ...
    def previous_day(self, line_user_id: str) -> list[Message]: ...
    def sessions(self) -> list[str]: ...
    def last_active(self, line_user_id: str) -> float | None: ...


class PgMemoryStore:
    """短期記憶的 Postgres（Supabase）實作；介面同 MemoryStore。"""

    def __init__(self, db: Database, clock: Callable[[], datetime], max_turns: int = 20) -> None:
        self._db = _Errors(db, lambda m: MemoryError(f"記憶存取失敗：{m}"))
        self._clock = clock
        self._max_turns = max_turns

    def append(self, line_user_id: str, message: Message) -> None:
        created_at = self._clock().timestamp()
        self._db.execute(
            "INSERT INTO turns (session_id, role, text, created_at) VALUES (%s, %s, %s, %s)",
            (line_user_id, message.role, message.text, created_at),
        )

    def recent(self, line_user_id: str) -> list[Message]:
        start = self._start_of_today()
        rows = self._db.query(
            "SELECT role, text FROM turns WHERE session_id = %s AND created_at >= %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (line_user_id, start, self._max_turns),
        )
        return [Message(role=r, text=t) for r, t in reversed(rows)]

    def previous_day(self, line_user_id: str) -> list[Message]:
        """整理批次用：回傳『剛結束的那一天』整天的對話（時序由舊到新）。"""
        start, end = previous_day_bounds(self._clock())
        rows = self._db.query(
            "SELECT role, text FROM turns "
            "WHERE session_id = %s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at ASC, id ASC LIMIT %s",
            (line_user_id, start, end, self._max_turns),
        )
        return [Message(role=r, text=t) for r, t in rows]

    def sessions(self) -> list[str]:
        rows = self._db.query("SELECT DISTINCT session_id FROM turns ORDER BY session_id")
        return [r[0] for r in rows]

    def last_active(self, line_user_id: str) -> float | None:
        row = self._db.query_one(
            "SELECT MAX(created_at) FROM turns WHERE session_id = %s AND role = 'user'",
            (line_user_id,),
        )
        return row[0] if row and row[0] is not None else None

    def _start_of_today(self) -> float:
        now = self._clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()
