"""知識圖譜事實儲存（SQLite，去重）。"""

from __future__ import annotations

import sqlite3
from typing import Protocol

from kinsun.knowledge.facts import Fact, FactCategory, Provenance


class KnowledgeError(Exception):
    """知識圖譜讀寫失敗。"""


class FactStore(Protocol):
    def add(self, fact: Fact) -> None: ...
    def all_for(self, session_id: str) -> list[Fact]: ...


class SqliteFactStore:
    def __init__(self, db_path: str) -> None:
        try:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS facts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "session_id TEXT NOT NULL, "
                "category TEXT NOT NULL, "
                "content TEXT NOT NULL, "
                "provenance TEXT NOT NULL, "
                "confidence REAL NOT NULL, "
                "UNIQUE(session_id, category, content))"
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise KnowledgeError(f"無法開啟知識圖譜資料庫：{exc}") from exc

    def add(self, fact: Fact) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO facts "
                "(session_id, category, content, provenance, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    fact.session_id,
                    fact.category.value,
                    fact.content,
                    fact.provenance.value,
                    fact.confidence,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise KnowledgeError(f"寫入事實失敗：{exc}") from exc

    def all_for(self, session_id: str) -> list[Fact]:
        try:
            rows = self._conn.execute(
                "SELECT category, content, provenance, confidence FROM facts "
                "WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise KnowledgeError(f"讀取事實失敗：{exc}") from exc
        return [
            Fact(session_id, FactCategory(cat), content, Provenance(prov), conf)
            for cat, content, prov, conf in rows
        ]
