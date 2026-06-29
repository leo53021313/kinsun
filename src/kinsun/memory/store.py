"""短期記憶（今日對話上下文）：以 Postgres（Supabase）持久化每輪對話。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from kinsun.db import connect
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
    def append(self, session_id: str, message: Message) -> None: ...
    def recent(self, session_id: str) -> list[Message]: ...
    def previous_day(self, session_id: str) -> list[Message]: ...
    def sessions(self) -> list[str]: ...
    def last_active(self, session_id: str) -> float | None: ...


class PgMemoryStore:
    """短期記憶的 Postgres（Supabase）實作；介面同 MemoryStore。"""

    def __init__(
        self, database_url: str, clock: Callable[[], datetime], max_turns: int = 20
    ) -> None:
        self._url = database_url
        self._clock = clock
        self._max_turns = max_turns

    def append(self, session_id: str, message: Message) -> None:
        created_at = self._clock().timestamp()
        try:
            with connect(self._url) as conn:
                conn.execute(
                    "INSERT INTO turns (session_id, role, text, created_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (session_id, message.role, message.text, created_at),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"寫入記憶失敗：{exc}") from exc

    def recent(self, session_id: str) -> list[Message]:
        start = self._start_of_today()
        try:
            with connect(self._url) as conn:
                rows = conn.execute(
                    "SELECT role, text FROM turns WHERE session_id = %s AND created_at >= %s "
                    "ORDER BY created_at DESC, id DESC LIMIT %s",
                    (session_id, start, self._max_turns),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"讀取記憶失敗：{exc}") from exc
        return [Message(role=r, text=t) for r, t in reversed(rows)]

    def previous_day(self, session_id: str) -> list[Message]:
        """整理批次用：回傳『剛結束的那一天』整天的對話（時序由舊到新）。"""
        start, end = previous_day_bounds(self._clock())
        try:
            with connect(self._url) as conn:
                rows = conn.execute(
                    "SELECT role, text FROM turns "
                    "WHERE session_id = %s AND created_at >= %s AND created_at < %s "
                    "ORDER BY created_at ASC, id ASC LIMIT %s",
                    (session_id, start, end, self._max_turns),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"讀取記憶失敗：{exc}") from exc
        return [Message(role=r, text=t) for r, t in rows]

    def sessions(self) -> list[str]:
        try:
            with connect(self._url) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT session_id FROM turns ORDER BY session_id"
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"列出 session 失敗：{exc}") from exc
        return [r[0] for r in rows]

    def last_active(self, session_id: str) -> float | None:
        try:
            with connect(self._url) as conn:
                row = conn.execute(
                    "SELECT MAX(created_at) FROM turns WHERE session_id = %s AND role = 'user'",
                    (session_id,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise MemoryError(f"查詢最後互動失敗：{exc}") from exc
        return row[0] if row and row[0] is not None else None

    def _start_of_today(self) -> float:
        now = self._clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()
