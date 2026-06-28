"""向量庫（SQLite 存向量、Python 餘弦搜尋）。"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Protocol


class VectorStoreError(Exception):
    """向量庫讀寫失敗。"""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class VectorStore(Protocol):
    def add(self, session_id: str, content: str, embedding: list[float]) -> None: ...
    def search(self, session_id: str, embedding: list[float], k: int) -> list[str]: ...


class SqliteVectorStore:
    def __init__(self, db_path: str) -> None:
        try:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS episodes ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "session_id TEXT NOT NULL, "
                "content TEXT NOT NULL, "
                "embedding TEXT NOT NULL, "
                "UNIQUE(session_id, content))"
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise VectorStoreError(f"無法開啟向量庫：{exc}") from exc

    def add(self, session_id: str, content: str, embedding: list[float]) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO episodes (session_id, content, embedding) VALUES (?, ?, ?)",
                (session_id, content, json.dumps(embedding)),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise VectorStoreError(f"寫入向量失敗：{exc}") from exc

    def search(self, session_id: str, embedding: list[float], k: int) -> list[str]:
        try:
            rows = self._conn.execute(
                "SELECT content, embedding FROM episodes WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise VectorStoreError(f"讀取向量失敗：{exc}") from exc
        scored = [(_cosine(embedding, json.loads(emb)), content) for content, emb in rows]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [content for _, content in scored[:k]]
