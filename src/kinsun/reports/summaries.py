"""對話摘要持久化：供日後對話報告查詢。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from kinsun.db import Database, _Errors

SUMMARY_PROMPT = (
    "你是協助家屬了解長輩近況的助手。請把以下長輩與『金孫』的對話，"
    "用一兩句溫暖、客觀的台灣繁體中文摘要長輩這天的狀況與情緒。"
    "只根據對話內容，不要編造未提及的事。"
)


@dataclass(frozen=True)
class ConversationSummary:
    session_id: str
    date: str
    content: str
    created_at: float


class ConversationSummaryError(Exception):
    """對話摘要讀寫失敗。"""


class ConversationSummaryStore(Protocol):
    def upsert(self, session_id: str, date: str, content: str) -> None: ...
    def list_for_session(self, session_id: str) -> list[ConversationSummary]: ...


class PgConversationSummaryStore:
    def __init__(self, db: Database, *, clock: Callable[[], datetime]) -> None:
        self._db = _Errors(db, lambda m: ConversationSummaryError(f"對話摘要存取失敗：{m}"))
        self._clock = clock

    def upsert(self, session_id: str, date: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO conversation_summaries (session_id, date, content, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (session_id, date) DO UPDATE SET "
            "content = EXCLUDED.content, created_at = EXCLUDED.created_at",
            (session_id, date, content, self._clock().timestamp()),
        )

    def list_for_session(self, session_id: str) -> list[ConversationSummary]:
        rows = self._db.query(
            "SELECT session_id, date, content, created_at FROM conversation_summaries "
            "WHERE session_id = %s ORDER BY date DESC",
            (session_id,),
        )
        return [ConversationSummary(*r) for r in rows]


def summarize_day(
    session_id: str,
    *,
    short_term,
    summarizer,
    summaries: ConversationSummaryStore,
    clock: Callable[[], datetime],
) -> None:
    turns = short_term.previous_day(session_id)
    if not turns:
        return
    content = summarizer.generate(system_prompt=SUMMARY_PROMPT, messages=turns)
    day = (clock().date() - timedelta(days=1)).isoformat()
    summaries.upsert(session_id, day, content)
