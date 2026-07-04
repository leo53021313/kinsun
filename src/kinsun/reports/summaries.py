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
    line_user_id: str
    date: str
    content: str
    created_at: float


class ConversationSummaryError(Exception):
    """對話摘要讀寫失敗。"""


class ConversationSummaryStore(Protocol):
    def save(self, line_user_id: str, date: str, content: str) -> None: ...
    def list_for_line_user(self, line_user_id: str) -> list[ConversationSummary]: ...


class PgConversationSummaryStore:
    def __init__(self, db: Database, *, clock: Callable[[], datetime]) -> None:
        self._db = _Errors(db, lambda m: ConversationSummaryError(f"對話摘要存取失敗：{m}"))
        self._clock = clock

    def save(self, line_user_id: str, date: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO conversation_summaries (line_user_id, date, content, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (line_user_id, date) DO UPDATE SET "
            "content = EXCLUDED.content, created_at = EXCLUDED.created_at",
            (line_user_id, date, content, self._clock().timestamp()),
        )

    def list_for_line_user(self, line_user_id: str) -> list[ConversationSummary]:
        rows = self._db.query(
            "SELECT line_user_id, date, content, created_at FROM conversation_summaries "
            "WHERE line_user_id = %s ORDER BY date DESC",
            (line_user_id,),
        )
        return [ConversationSummary(*r) for r in rows]


class FakeConversationSummaryStore:
    """ConversationSummaryStore 的記憶體替身（測試用，不碰 DB）。

    save 以 (line_user_id, date) 為鍵做 upsert；list_for_line_user 依 date
    由新到舊排序，與 PgConversationSummaryStore 的 ON CONFLICT (line_user_id, date)
    與 ORDER BY date DESC 對齊。date 為 ISO 字串故字典序即日期序。
    created_at 一律填 0.0（Pg 由 clock 決定）；合約僅斷言 content／date／排序，
    此欄位不影響兩者對等性。
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], str] = {}

    def save(self, line_user_id: str, date: str, content: str) -> None:
        self._rows[(line_user_id, date)] = content

    def list_for_line_user(self, line_user_id: str) -> list[ConversationSummary]:
        items = sorted(
            ((d, c) for (s, d), c in self._rows.items() if s == line_user_id),
            key=lambda x: x[0],
            reverse=True,
        )
        return [ConversationSummary(line_user_id, d, c, 0.0) for d, c in items]


def summarize_day(
    line_user_id: str,
    *,
    short_term,
    summarizer,
    summaries: ConversationSummaryStore,
    clock: Callable[[], datetime],
) -> None:
    turns = short_term.previous_day(line_user_id)
    if not turns:
        return
    content = summarizer.generate(system_prompt=SUMMARY_PROMPT, messages=turns)
    day = (clock().date() - timedelta(days=1)).isoformat()
    summaries.save(line_user_id, day, content)
