"""短期記憶（今日對話上下文）：以 SQLite 持久化每輪對話。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun.llm import Message


class MemoryError(Exception):
    """短期記憶讀寫失敗。"""


class MemoryStore(Protocol):
    def append(self, session_id: str, message: Message) -> None: ...
    def recent(self, session_id: str) -> list[Message]: ...


class SqliteMemoryStore:
    def __init__(self, db_path: str, clock: Callable[[], datetime], max_turns: int = 20) -> None:
        self._clock = clock
        self._max_turns = max_turns
        try:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS turns ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "session_id TEXT NOT NULL, "
                "role TEXT NOT NULL, "
                "text TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise MemoryError(f"無法開啟記憶資料庫：{exc}") from exc

    def append(self, session_id: str, message: Message) -> None:
        created_at = self._clock().timestamp()
        try:
            self._conn.execute(
                "INSERT INTO turns (session_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                (session_id, message.role, message.text, created_at),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise MemoryError(f"寫入記憶失敗：{exc}") from exc

    def recent(self, session_id: str) -> list[Message]:
        start = self._start_of_today()
        try:
            rows = self._conn.execute(
                "SELECT role, text FROM turns "
                "WHERE session_id = ? AND created_at >= ? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (session_id, start, self._max_turns),
            ).fetchall()
        except sqlite3.Error as exc:
            raise MemoryError(f"讀取記憶失敗：{exc}") from exc
        return [Message(role=role, text=text) for role, text in reversed(rows)]

    def _start_of_today(self) -> float:
        now = self._clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()
