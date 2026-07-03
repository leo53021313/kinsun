"""觀測資料持久化：各階段專表的 append-only 記錄與後台查詢。

record_* 為 append-only 寫入；查詢供 web/admin_api 使用。
呼叫端埋點一律以 safe_record 包裹——觀測失敗絕不中斷對話。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from psycopg.types.json import Json

from kinsun.db import Database, _Errors
from kinsun.observability.models import (
    AsrCall,
    ElderActivity,
    FeedItem,
    LlmCall,
    OverviewStats,
    Reply,
    TimelineItem,
    Trace,
    TraceRiskEvent,
    TtsCall,
    WebhookEvent,
)

logger = logging.getLogger("kinsun.observability")


class TraceError(Exception):
    """觀測資料讀寫失敗。"""


def safe_record(action: Callable[[], None]) -> None:
    """觀測記錄失敗絕不中斷對話：吞掉所有例外、只留 warning。"""
    try:
        action()
    except Exception:  # noqa: BLE001 - 觀測失敗不可影響主流程
        logger.warning("觀測記錄落庫失敗", exc_info=True)


class TraceStore(Protocol):
    def record_webhook_event(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        event_type: str,
        message_type: str,
        payload: dict,
    ) -> None: ...
    def record_asr_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        transcript: str,
        source_audio_url: str,
        error_message: str,
    ) -> None: ...
    def record_llm_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        model_name: str,
        input_tokens: int | None,
        output_tokens: int | None,
        content: str,
        error_message: str,
    ) -> None: ...
    def record_tts_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        content: str,
        error_message: str,
    ) -> None: ...
    def record_reply(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        kind: str,
        status: str,
        latency_ms: int,
        audio_url: str,
    ) -> None: ...
    def get_trace(self, trace_id: str) -> Trace | None: ...
    def list_feed(self, *, after: float, limit: int) -> list[FeedItem]: ...
    def list_timeline_for_elder(
        self,
        *,
        elder_id: str,
        line_user_id: str,
        start: float,
        end: float,
    ) -> list[TimelineItem]: ...
    def list_elders_with_last_active(self) -> list[ElderActivity]: ...
    def get_overview_stats(
        self,
        *,
        today_start: float,
        hourly_start: float,
    ) -> OverviewStats: ...
    def purge_older_than(self, cutoff: float) -> None: ...


class PgTraceStore:
    """TraceStore 的 Postgres（Supabase）實作。"""

    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: TraceError(f"觀測資料存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def _now(self) -> float:
        return self._clock().timestamp()

    def record_webhook_event(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        event_type: str,
        message_type: str,
        payload: dict,
    ) -> None:
        self._db.execute(
            "INSERT INTO webhook_events (webhook_event_id, trace_id, line_user_id, "
            "event_type, message_type, payload, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                line_user_id,
                event_type,
                message_type,
                Json(payload),
                self._now(),
            ),
        )

    def record_asr_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        transcript: str,
        source_audio_url: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO asr_calls (asr_call_id, trace_id, line_user_id, status, "
            "latency_ms, transcript, source_audio_url, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                transcript,
                source_audio_url,
                error_message,
                self._now(),
            ),
        )

    def record_llm_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        model_name: str,
        input_tokens: int | None,
        output_tokens: int | None,
        content: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO llm_calls (llm_call_id, trace_id, line_user_id, status, "
            "latency_ms, model_name, input_tokens, output_tokens, content, "
            "error_message, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                model_name,
                input_tokens,
                output_tokens,
                content,
                error_message,
                self._now(),
            ),
        )

    def record_tts_call(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        status: str,
        latency_ms: int,
        content: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO tts_calls (tts_call_id, trace_id, line_user_id, status, "
            "latency_ms, content, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                content,
                error_message,
                self._now(),
            ),
        )

    def record_reply(
        self,
        *,
        trace_id: str,
        line_user_id: str,
        kind: str,
        status: str,
        latency_ms: int,
        audio_url: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO replies (reply_id, trace_id, line_user_id, kind, status, "
            "latency_ms, audio_url, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                line_user_id,
                kind,
                status,
                latency_ms,
                audio_url,
                self._now(),
            ),
        )

    def get_trace(self, trace_id: str) -> Trace | None:
        webhook_row = self._db.query_one(
            "SELECT webhook_event_id, trace_id, line_user_id, event_type, message_type, "
            "payload, created_at FROM webhook_events WHERE trace_id = %s "
            "ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        asr_row = self._db.query_one(
            "SELECT asr_call_id, trace_id, line_user_id, status, latency_ms, transcript, "
            "source_audio_url, error_message, created_at FROM asr_calls "
            "WHERE trace_id = %s ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        llm_rows = self._db.query(
            "SELECT llm_call_id, trace_id, line_user_id, status, latency_ms, model_name, "
            "input_tokens, output_tokens, content, error_message, created_at "
            "FROM llm_calls WHERE trace_id = %s ORDER BY created_at",
            (trace_id,),
        )
        tts_row = self._db.query_one(
            "SELECT tts_call_id, trace_id, line_user_id, status, latency_ms, content, "
            "error_message, created_at FROM tts_calls WHERE trace_id = %s "
            "ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        reply_row = self._db.query_one(
            "SELECT reply_id, trace_id, line_user_id, kind, status, latency_ms, "
            "audio_url, created_at FROM replies WHERE trace_id = %s "
            "ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        risk_rows = self._db.query(
            "SELECT tier, reason, created_at FROM risk_events WHERE trace_id = %s "
            "ORDER BY created_at",
            (trace_id,),
        )
        webhook_event = WebhookEvent(*webhook_row) if webhook_row else None
        asr_call = AsrCall(*asr_row) if asr_row else None
        llm_calls = [LlmCall(*r) for r in llm_rows]
        tts_call = TtsCall(*tts_row) if tts_row else None
        reply = Reply(*reply_row) if reply_row else None
        risk_events = [TraceRiskEvent(*r) for r in risk_rows]
        if not any([webhook_event, asr_call, llm_calls, tts_call, reply, risk_events]):
            return None
        line_user_id = next(
            (x.line_user_id for x in [webhook_event, asr_call, tts_call, reply] if x),
            llm_calls[0].line_user_id if llm_calls else "",
        )
        return Trace(
            trace_id=trace_id,
            line_user_id=line_user_id,
            webhook_event=webhook_event,
            asr_call=asr_call,
            llm_calls=llm_calls,
            tts_call=tts_call,
            reply=reply,
            risk_events=risk_events,
        )

    def list_feed(self, *, after: float, limit: int) -> list[FeedItem]:
        rows = self._db.query(
            "SELECT 'turn' AS kind, t.line_user_id, COALESCE(e.name, ''), t.role, "
            "t.content, NULL::integer AS tier, NULL::text AS trace_id, t.created_at "
            "FROM turns t LEFT JOIN elders e ON e.line_user_id = t.line_user_id "
            "WHERE t.created_at > %s "
            "UNION ALL "
            "SELECT 'reminder', COALESCE(e.line_user_id, ''), COALESCE(e.name, ''), '', "
            "r.content, NULL, NULL, r.created_at "
            "FROM reminder_logs r LEFT JOIN elders e ON e.elder_id = r.elder_id "
            "WHERE r.created_at > %s "
            "UNION ALL "
            "SELECT 'risk', k.line_user_id, COALESCE(e.name, ''), '', k.reason, "
            "k.tier, k.trace_id, k.created_at "
            "FROM risk_events k LEFT JOIN elders e ON e.line_user_id = k.line_user_id "
            "WHERE k.created_at > %s "
            "ORDER BY created_at DESC LIMIT %s",
            (after, after, after, limit),
        )
        return [FeedItem(*r) for r in rows]

    def list_timeline_for_elder(
        self,
        *,
        elder_id: str,
        line_user_id: str,
        start: float,
        end: float,
    ) -> list[TimelineItem]:
        rows = self._db.query(
            "SELECT 'turn' AS kind, t.role, t.content, NULL::integer AS tier, "
            "NULL::text AS trace_id, '' AS audio_url, t.created_at "
            "FROM turns t WHERE t.line_user_id = %s AND t.created_at >= %s "
            "AND t.created_at < %s "
            "UNION ALL "
            "SELECT 'reminder', '', r.content, NULL, NULL, '', r.created_at "
            "FROM reminder_logs r WHERE r.elder_id = %s AND r.created_at >= %s "
            "AND r.created_at < %s "
            "UNION ALL "
            "SELECT 'risk', '', k.reason, k.tier, k.trace_id, '', k.created_at "
            "FROM risk_events k WHERE k.line_user_id = %s AND k.created_at >= %s "
            "AND k.created_at < %s "
            "UNION ALL "
            "SELECT 'voice', 'user', a.transcript, NULL, a.trace_id, "
            "a.source_audio_url, a.created_at "
            "FROM asr_calls a WHERE a.line_user_id = %s AND a.created_at >= %s "
            "AND a.created_at < %s "
            "UNION ALL "
            "SELECT 'voice', 'assistant', '', NULL, p.trace_id, p.audio_url, p.created_at "
            "FROM replies p WHERE p.line_user_id = %s AND p.audio_url <> '' "
            "AND p.created_at >= %s AND p.created_at < %s "
            "ORDER BY created_at",
            (
                line_user_id,
                start,
                end,
                elder_id,
                start,
                end,
                line_user_id,
                start,
                end,
                line_user_id,
                start,
                end,
                line_user_id,
                start,
                end,
            ),
        )
        return [TimelineItem(*r) for r in rows]

    def list_elders_with_last_active(self) -> list[ElderActivity]:
        rows = self._db.query(
            "SELECT e.elder_id, e.name, COALESCE(e.line_user_id, ''), "
            "(SELECT MAX(t.created_at) FROM turns t "
            " WHERE t.line_user_id = e.line_user_id) "
            "FROM elders e ORDER BY e.name",
        )
        return [ElderActivity(*r) for r in rows]

    # get_overview_stats／purge_older_than 由後續任務實作。
