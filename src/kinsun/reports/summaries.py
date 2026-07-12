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
    elder_id: str
    date: str
    content: str
    created_at: float


class ConversationSummaryError(Exception):
    """對話摘要讀寫失敗。"""


class ConversationSummaryStore(Protocol):
    def save(self, elder_id: str, date: str, content: str) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[ConversationSummary]: ...


class PgConversationSummaryStore:
    def __init__(self, db: Database, *, clock: Callable[[], datetime]) -> None:
        self._db = _Errors(db, lambda m: ConversationSummaryError(f"對話摘要存取失敗：{m}"))
        self._clock = clock

    def save(self, elder_id: str, date: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO conversation_summaries (elder_id, date, content, created_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (elder_id, date) WHERE elder_id IS NOT NULL DO UPDATE SET "
            "content = EXCLUDED.content, created_at = EXCLUDED.created_at",
            (elder_id, date, content, self._clock().timestamp()),
        )

    def list_for_elder(self, elder_id: str) -> list[ConversationSummary]:
        rows = self._db.query(
            "SELECT elder_id, date, content, created_at FROM conversation_summaries "
            "WHERE elder_id = %s ORDER BY date DESC",
            (elder_id,),
        )
        return [ConversationSummary(*r) for r in rows]


class FakeConversationSummaryStore:
    """ConversationSummaryStore 的記憶體替身（測試用，不碰 DB）。

    save 以 (elder_id, date) 為鍵做 upsert；list_for_elder 依 date
    由新到舊排序，與 PgConversationSummaryStore 的 ON CONFLICT (elder_id, date)
    與 ORDER BY date DESC 對齊。date 為 ISO 字串故字典序即日期序。
    created_at 一律填 0.0（Pg 由 clock 決定）；合約僅斷言 content／date／排序，
    此欄位不影響兩者對等性。
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], str] = {}

    def save(self, elder_id: str, date: str, content: str) -> None:
        self._rows[(elder_id, date)] = content

    def list_for_elder(self, elder_id: str) -> list[ConversationSummary]:
        items = sorted(
            ((d, c) for (s, d), c in self._rows.items() if s == elder_id),
            key=lambda x: x[0],
            reverse=True,
        )
        return [ConversationSummary(elder_id, d, c, 0.0) for d, c in items]


def _l1_signals_for_day(risk_events, elder_id: str, now: datetime) -> list[str]:
    """取摘要日（昨天）的 L1 小訊號理由（✅ D-10 己-5）。

    只取 L1：L2 已即時通知過家屬，不重複；fail-safe 留痕（分級器故障）是系統
    事件、不是長輩狀態，不進家屬摘要。台灣無日光節約時間，一天固定 86400 秒。
    """
    from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskTier

    day = now.date() - timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=now.tzinfo).timestamp()
    end = start + 86400.0
    return [
        e.reason
        for e in reversed(risk_events.list_for_elder(elder_id))  # 由舊到新
        if e.tier == RiskTier.L1
        and e.reason != FAILSAFE_EVENT_REASON
        and start <= e.created_at < end
    ]


def summarize_day(
    elder_id: str,
    *,
    short_term,
    summarizer,
    summaries: ConversationSummaryStore,
    clock: Callable[[], datetime],
    risk_events=None,
) -> None:
    turns = short_term.previous_day(elder_id)
    if not turns:
        return
    system_prompt = SUMMARY_PROMPT
    signals = _l1_signals_for_day(risk_events, elder_id, clock()) if risk_events else []
    if signals:
        # L1 小訊號進每日摘要（✅ D-10 己-5）：不即時通知、改讓家人在摘要看到。
        system_prompt += (
            "另外，系統當天記錄到這些健康或情緒上的小訊號（非緊急）："
            + "；".join(signals)
            + "。請在摘要中自然地一併提及，讓家人知道可以多關心。"
        )
    content = summarizer.generate(system_prompt=system_prompt, messages=turns)
    day = (clock().date() - timedelta(days=1)).isoformat()
    summaries.save(elder_id, day, content)
