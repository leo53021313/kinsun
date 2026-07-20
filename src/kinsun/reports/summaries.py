"""對話摘要持久化：供日後對話報告查詢。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from kinsun import tracing
from kinsun.db import Database, _Errors
from kinsun.llm import LLMError, Message

SUMMARY_PROMPT = (
    "你是協助家屬了解長輩近況的助手。請把使用者提供的長輩與『金孫』對話紀錄，"
    "用一兩句溫暖、客觀的台灣繁體中文摘要長輩這天的狀況與情緒。"
    "只根據對話內容，不要編造未提及的事；直接輸出摘要正文，"
    "不要標題、粗體、分隔線或任何 Markdown 符號。"
)

_ROLE_LABELS = {"user": "長輩", "assistant": "金孫"}

_TRANSCRIPT_PROMPT = "以下是長輩與『金孫』當天的對話紀錄：\n{transcript}\n請依上述要求輸出摘要。"

# 生成失敗（空回應、接話）重試次數：實測 2026-07-17 空回應率 39%，重試一次可將
# 失敗率壓到約 15%；夜間批次逐位長輩執行，再多重試效益遞減。
_SUMMARY_ATTEMPTS = 2


def _transcript_message(turns: list[Message]) -> Message:
    """把整天對話組成單一 user 文字稿訊息。

    為什麼不把對話當 user/assistant 歷史直接餵：模型會把自己當成對話中的人
    「接話」（實測 2026-07-17 回出「心情有沒有比較好？」）或直接回空——它看到
    的是一場進行中的對話，不是一份待摘要的紀錄。文字稿讓它站在旁觀者位置。
    """
    lines = "\n".join(f"{_ROLE_LABELS.get(m.role, '金孫')}：{m.content}" for m in turns)
    return Message("user", _TRANSCRIPT_PROMPT.format(transcript=lines))


_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_MARKDOWN_CHARS = re.compile(r"[*#`＊]+")


def _clean_summary(raw: str) -> str:
    """去掉實測（2026-07-17）出現過的格式垃圾：Markdown 粗體與分隔線、
    HTML 標籤（</blockquote>）、標題行與指令複述行（「請提供這段對話的摘要。」）。"""
    text = _MARKDOWN_CHARS.sub("", _HTML_TAG.sub("", raw))
    lines = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if line.endswith("："):  # 「長輩今日狀況摘要：」這類標題行
            continue
        if "請提供" in line or line.startswith("請幫我"):  # 指令複述／要求補資料
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _is_usable_summary(content: str) -> bool:
    """擋掉「接話」產物：實測失敗樣本皆為 25 字內的短問句（如「心情有沒有比較好？」）。"""
    if not content:
        return False
    return not (content.endswith(("？", "?")) and len(content) < 25)


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
    def get_for_date(self, elder_id: str, date: str) -> ConversationSummary | None: ...
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

    def get_for_date(self, elder_id: str, date: str) -> ConversationSummary | None:
        """取某天的摘要；那天沒講話（summarize_day 未存列）回 None。

        主動推播讀「她上次開口那天」的摘要用（spec 2026-07-17）。不重用
        list_for_elder 再過濾：它無 limit，為了一列而全撈該長輩數百列摘要。
        """
        row = self._db.query_one(
            "SELECT elder_id, date, content, created_at FROM conversation_summaries "
            "WHERE elder_id = %s AND date = %s",
            (elder_id, date),
        )
        return ConversationSummary(*row) if row else None

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

    def get_for_date(self, elder_id: str, date: str) -> ConversationSummary | None:
        content = self._rows.get((elder_id, date))
        return ConversationSummary(elder_id, date, content, 0.0) if content is not None else None

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


@tracing.track(name="daily_summary", type="general", capture_input=False, capture_output=False)
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
    tracing.update_trace_metadata(elder_id=elder_id, flow="daily_summary")
    system_prompt = SUMMARY_PROMPT
    signals = _l1_signals_for_day(risk_events, elder_id, clock()) if risk_events else []
    if signals:
        # L1 小訊號進每日摘要（✅ D-10 己-5）：不即時通知、改讓家人在摘要看到。
        system_prompt += (
            "另外，系統當天記錄到這些健康或情緒上的小訊號（非緊急）："
            + "；".join(signals)
            + "。請在摘要中自然地一併提及，讓家人知道可以多關心。"
        )
    request = [_transcript_message(turns)]
    last_error: LLMError | None = None
    content = ""
    for _ in range(_SUMMARY_ATTEMPTS):
        try:
            raw = summarizer.generate(system_prompt=system_prompt, messages=request)
        except LLMError as exc:
            last_error = exc
            continue
        content = _clean_summary(raw)
        if _is_usable_summary(content):
            break
        content = ""
    if not content:
        # 冒到 fanout 的 per-item 接手（跳過該長輩、留 log），與重試前的失敗語意一致。
        raise last_error or LLMError("摘要生成不合格（空白或接話），重試後仍失敗")
    # 摘要文字攤在本層 span（raw LLM I/O 已在 wrap_genai 子 span，這裡放後處理的成品）。
    tracing.set_current_span_io(span_output={"summary": content})
    day = (clock().date() - timedelta(days=1)).isoformat()
    summaries.save(elder_id, day, content)
