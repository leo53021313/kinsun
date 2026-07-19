"""觀測資料持久化：各階段專表的 append-only 記錄與後台查詢。

record_* 為 append-only 寫入；查詢供 web/routers/admin 使用。
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
    HourlyCount,
    LlmCall,
    OverviewStats,
    RagCall,
    Reply,
    StageStats,
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
        external_id: str,
        channel: str = "",
        event_type: str,
        message_type: str,
        payload: dict,
    ) -> None: ...
    def record_asr_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
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
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        model_name: str,
        input_tokens: int | None,
        output_tokens: int | None,
        content: str,
        error_message: str,
    ) -> None: ...
    def record_rag(
        self,
        *,
        trace_id: str,
        elder_id: str,
        query: str,
        index_version: str,
        status: str,
        latency_ms: int,
        safety_level: str,
        reason: str,
        hits: list[dict],
        citations: list[dict],
    ) -> None: ...
    def record_tts_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        content: str,
        error_message: str,
    ) -> None: ...
    def record_reply(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        kind: str,
        status: str,
        latency_ms: int,
        round_trip_ms: int | None = None,
        audio_url: str,
    ) -> None: ...
    def get_trace(self, trace_id: str) -> Trace | None: ...
    def list_feed(
        self, *, after: float, before: float | None = None, limit: int
    ) -> list[FeedItem]: ...
    def list_timeline_for_elder(
        self,
        *,
        elder_id: str,
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
        external_id: str,
        channel: str = "",
        event_type: str,
        message_type: str,
        payload: dict,
    ) -> None:
        self._db.execute(
            "INSERT INTO webhook_events (webhook_event_id, trace_id, external_id, channel, "
            "event_type, message_type, payload, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                external_id,
                channel,
                event_type,
                message_type,
                Json(payload),
                self._now(),
            ),
        )

    def record_rag(
        self,
        *,
        trace_id: str,
        elder_id: str,
        query: str,
        index_version: str,
        status: str,
        latency_ms: int,
        safety_level: str,
        reason: str,
        hits: list[dict],
        citations: list[dict],
    ) -> None:
        self._db.execute(
            "INSERT INTO rag_calls (rag_call_id, trace_id, elder_id, query, index_version, "
            "status, latency_ms, safety_level, reason, hits, citations, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                self._new_id(),
                trace_id,
                elder_id,
                query,
                index_version,
                status,
                latency_ms,
                safety_level,
                reason,
                Json(hits),
                Json(citations),
                self._now(),
            ),
        )

    def record_asr_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        transcript: str,
        source_audio_url: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO asr_calls (asr_call_id, trace_id, external_id, channel, status, "
            "latency_ms, transcript, source_audio_url, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                external_id,
                channel,
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
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        model_name: str,
        input_tokens: int | None,
        output_tokens: int | None,
        content: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO llm_calls (llm_call_id, trace_id, external_id, channel, status, "
            "latency_ms, model_name, input_tokens, output_tokens, content, "
            "error_message, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                external_id,
                channel,
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
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        content: str,
        error_message: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO tts_calls (tts_call_id, trace_id, external_id, channel, status, "
            "latency_ms, content, error_message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                external_id,
                channel,
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
        external_id: str,
        channel: str = "",
        kind: str,
        status: str,
        latency_ms: int,
        round_trip_ms: int | None = None,
        audio_url: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO replies (reply_id, trace_id, external_id, channel, kind, status, "
            "latency_ms, round_trip_ms, audio_url, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                trace_id,
                external_id,
                channel,
                kind,
                status,
                latency_ms,
                round_trip_ms,
                audio_url,
                self._now(),
            ),
        )

    def get_trace(self, trace_id: str) -> Trace | None:
        webhook_row = self._db.query_one(
            "SELECT webhook_event_id, trace_id, external_id, channel, event_type, message_type, "
            "payload, created_at FROM webhook_events WHERE trace_id = %s "
            "ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        asr_row = self._db.query_one(
            "SELECT asr_call_id, trace_id, external_id, channel, status, latency_ms, transcript, "
            "source_audio_url, error_message, created_at FROM asr_calls "
            "WHERE trace_id = %s ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        llm_rows = self._db.query(
            "SELECT llm_call_id, trace_id, external_id, channel, status, latency_ms, model_name, "
            "input_tokens, output_tokens, content, error_message, created_at "
            "FROM llm_calls WHERE trace_id = %s ORDER BY created_at",
            (trace_id,),
        )
        rag_rows = self._db.query(
            "SELECT rag_call_id, trace_id, elder_id, query, index_version, status, latency_ms, "
            "safety_level, reason, hits, citations, created_at "
            "FROM rag_calls WHERE trace_id = %s ORDER BY created_at",
            (trace_id,),
        )
        tts_row = self._db.query_one(
            "SELECT tts_call_id, trace_id, external_id, channel, status, latency_ms, content, "
            "error_message, created_at FROM tts_calls WHERE trace_id = %s "
            "ORDER BY created_at LIMIT 1",
            (trace_id,),
        )
        reply_row = self._db.query_one(
            "SELECT reply_id, trace_id, external_id, channel, kind, status, latency_ms, "
            "round_trip_ms, audio_url, created_at FROM replies WHERE trace_id = %s "
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
        rag_calls = [RagCall(*r) for r in rag_rows]
        tts_call = TtsCall(*tts_row) if tts_row else None
        reply = Reply(*reply_row) if reply_row else None
        risk_events = [TraceRiskEvent(*r) for r in risk_rows]
        if not any([webhook_event, asr_call, llm_calls, rag_calls, tts_call, reply, risk_events]):
            return None
        rows_with_source = [webhook_event, asr_call, tts_call, reply, *llm_calls]
        external_id = next((x.external_id for x in rows_with_source if x), "")
        channel = next((x.channel for x in rows_with_source if x), "")
        name_row = self._db.query_one(
            "SELECT e.name FROM channel_bindings b JOIN elders e ON e.elder_id = b.principal_id "
            "WHERE b.external_id = %s AND b.principal_type = 'elder' LIMIT 1",
            (external_id,),
        )
        if name_row is None and rag_calls:
            name_row = self._db.query_one(
                "SELECT name FROM elders WHERE elder_id = %s LIMIT 1",
                (rag_calls[0].elder_id,),
            )
        return Trace(
            trace_id=trace_id,
            external_id=external_id,
            channel=channel,
            webhook_event=webhook_event,
            asr_call=asr_call,
            llm_calls=llm_calls,
            rag_calls=rag_calls,
            tts_call=tts_call,
            reply=reply,
            risk_events=risk_events,
            elder_name=name_row[0] if name_row else "",
        )

    def list_feed(self, *, after: float, before: float | None = None, limit: int) -> list[FeedItem]:
        # before（✅ D-29 回翻歷史）為選配上界：created_at < before；游標值＝epoch 秒。
        def cond(alias: str) -> str:
            base = f"{alias}.created_at > %s"
            return base + (f" AND {alias}.created_at < %s" if before is not None else "")

        one = (after,) if before is None else (after, before)
        rows = self._db.query(
            "SELECT 'turn' AS kind, COALESCE(t.elder_id, ''), COALESCE(e.name, ''), t.role, "
            "t.content, NULL::integer AS tier, NULL::text AS trace_id, t.created_at "
            "FROM turns t LEFT JOIN elders e ON e.elder_id = t.elder_id "
            f"WHERE {cond('t')} "
            "UNION ALL "
            "SELECT 'reminder', r.elder_id, COALESCE(e.name, ''), '', "
            "r.content, NULL, NULL, r.created_at "
            "FROM reminder_logs r LEFT JOIN elders e ON e.elder_id = r.elder_id "
            f"WHERE {cond('r')} "
            "UNION ALL "
            "SELECT 'risk', COALESCE(k.elder_id, ''), COALESCE(e.name, ''), '', k.reason, "
            "k.tier, k.trace_id, k.created_at "
            "FROM risk_events k LEFT JOIN elders e ON e.elder_id = k.elder_id "
            f"WHERE {cond('k')} "
            "ORDER BY created_at DESC LIMIT %s",
            (*one, *one, *one, limit),
        )
        return [FeedItem(*r) for r in rows]

    def list_timeline_for_elder(
        self,
        *,
        elder_id: str,
        start: float,
        end: float,
    ) -> list[TimelineItem]:
        # turns／risk_events 已以 elder_id 為鍵；觀測五表（asr_calls／replies）維持通道識別，
        # 經 channel_bindings 把 external_id 映回本人。
        rows = self._db.query(
            "SELECT 'turn' AS kind, t.role, t.content, NULL::integer AS tier, "
            "NULL::text AS trace_id, '' AS audio_url, t.created_at "
            "FROM turns t WHERE t.elder_id = %s AND t.created_at >= %s "
            "AND t.created_at < %s "
            "UNION ALL "
            "SELECT 'reminder', '', r.content, NULL, NULL, '', r.created_at "
            "FROM reminder_logs r WHERE r.elder_id = %s AND r.created_at >= %s "
            "AND r.created_at < %s "
            "UNION ALL "
            "SELECT 'risk', '', k.reason, k.tier, k.trace_id, '', k.created_at "
            "FROM risk_events k WHERE k.elder_id = %s AND k.created_at >= %s "
            "AND k.created_at < %s "
            "UNION ALL "
            "SELECT 'voice', 'user', a.transcript, NULL, a.trace_id, "
            "a.source_audio_url, a.created_at "
            "FROM asr_calls a JOIN channel_bindings b ON b.external_id = a.external_id "
            "AND b.principal_type = 'elder' AND b.principal_id = %s "
            "WHERE a.created_at >= %s AND a.created_at < %s "
            "UNION ALL "
            "SELECT 'voice', 'assistant', '', NULL, p.trace_id, p.audio_url, p.created_at "
            "FROM replies p JOIN channel_bindings b ON b.external_id = p.external_id "
            "AND b.principal_type = 'elder' AND b.principal_id = %s "
            "WHERE p.audio_url <> '' AND p.created_at >= %s AND p.created_at < %s "
            "ORDER BY created_at",
            (
                elder_id,
                start,
                end,
                elder_id,
                start,
                end,
                elder_id,
                start,
                end,
                elder_id,
                start,
                end,
                elder_id,
                start,
                end,
            ),
        )
        return [TimelineItem(*r) for r in rows]

    def list_elders_with_last_active(self) -> list[ElderActivity]:
        rows = self._db.query(
            "SELECT e.elder_id, e.name, "
            "(SELECT COALESCE(string_agg(DISTINCT b.channel, ','), '') FROM channel_bindings b "
            " WHERE b.principal_type = 'elder' AND b.principal_id = e.elder_id), "
            "(SELECT MAX(t.created_at) FROM turns t WHERE t.elder_id = e.elder_id) "
            "FROM elders e ORDER BY e.name",
        )
        return [ElderActivity(*r) for r in rows]

    def get_overview_stats(
        self,
        *,
        today_start: float,
        hourly_start: float,
    ) -> OverviewStats:
        # 活躍長輩以 elder_id 計（✅ D-34 丙-4）：turns 的舊 line_user_id 欄已退役恆 NULL。
        turn_row = self._db.query_one(
            "SELECT COUNT(*), COUNT(DISTINCT elder_id) FROM turns WHERE created_at >= %s",
            (today_start,),
        )
        risk_row = self._db.query_one(
            "SELECT COUNT(*) FROM risk_events WHERE created_at >= %s", (today_start,)
        )
        token_row = self._db.query_one(
            "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) "
            "FROM llm_calls WHERE created_at >= %s",
            (today_start,),
        )
        stages = []
        for stage, table in (("asr", "asr_calls"), ("llm", "llm_calls"), ("tts", "tts_calls")):
            # 表名為固定白名單、非外部輸入，f-string 無注入風險。
            row = self._db.query_one(
                f"SELECT COUNT(*), COUNT(*) FILTER (WHERE status <> 'ok'), "
                f"COALESCE(AVG(latency_ms), 0), "
                f"COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms), 0), "
                f"COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) "
                f"FROM {table} WHERE created_at >= %s",
                (today_start,),
            )
            stages.append(
                StageStats(stage, row[0], row[1], float(row[2]), float(row[3]), float(row[4]))
            )
        # 端到端往返（✅ D-05 戊-2）：round_trip_ms 為 NULL（未量測）者不計。
        row = self._db.query_one(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE status <> 'ok'), "
            "COALESCE(AVG(round_trip_ms), 0), "
            "COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY round_trip_ms), 0), "
            "COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY round_trip_ms), 0) "
            "FROM replies WHERE created_at >= %s AND round_trip_ms IS NOT NULL",
            (today_start,),
        )
        stages.append(
            StageStats("round_trip", row[0], row[1], float(row[2]), float(row[3]), float(row[4]))
        )
        hourly_rows = self._db.query(
            "SELECT floor(created_at / 3600) * 3600 AS hour_start, COUNT(*) "
            "FROM turns WHERE created_at >= %s GROUP BY 1 ORDER BY 1",
            (hourly_start,),
        )
        return OverviewStats(
            turn_count=turn_row[0],
            risk_event_count=risk_row[0],
            active_elder_count=turn_row[1],
            llm_input_tokens=int(token_row[0]),
            llm_output_tokens=int(token_row[1]),
            stages=stages,
            hourly_turns=[HourlyCount(float(h), n) for h, n in hourly_rows],
        )

    def purge_older_than(self, cutoff: float) -> None:
        # 表名為固定白名單、非外部輸入，f-string 無注入風險。
        for table in (
            "webhook_events",
            "asr_calls",
            "llm_calls",
            "rag_calls",
            "tts_calls",
            "replies",
        ):
            self._db.execute(f"DELETE FROM {table} WHERE created_at < %s", (cutoff,))


class FakeTraceStore:
    """TraceStore 的記憶體替身（測試用，不碰 DB）。

    記錄存於公開 list；``now`` 屬性控制 record_* 寫入的 created_at。
    seed_* 方法模擬既有表（turns／reminder_logs／risk_events／elders）資料，
    供查詢面（feed／timeline／overview）測試播種。
    """

    def __init__(self) -> None:
        self.now = 0.0
        self._seq = 0
        self.webhook_events: list[WebhookEvent] = []
        self.asr_calls: list[AsrCall] = []
        self.llm_calls: list[LlmCall] = []
        self.rag_calls: list[RagCall] = []
        self.tts_calls: list[TtsCall] = []
        self.replies: list[Reply] = []
        # (elder_id, role, content, created_at)
        self.turns: list[tuple[str, str, str, float]] = []
        # (elder_id, kind, content, created_at)
        self.reminders: list[tuple[str, str, str, float]] = []
        # (elder_id, tier, reason, created_at, trace_id)
        self.risks: list[tuple[str, int, str, float, str | None]] = []
        # (elder_id, name)
        self.elders: list[tuple[str, str]] = []
        # (external_id, elder_id)：channel_bindings 的長輩綁定（voice 時間軸／trace 姓名映射用）
        self.channel_bindings: list[tuple[str, str]] = []

    def _next_id(self) -> str:
        self._seq += 1
        return f"obs{self._seq}"

    # --- 播種（模擬既有表） ---

    def seed_turn(self, elder_id: str, role: str, content: str, created_at: float) -> None:
        self.turns.append((elder_id, role, content, created_at))

    def seed_reminder(self, elder_id: str, kind: str, content: str, created_at: float) -> None:
        self.reminders.append((elder_id, kind, content, created_at))

    def seed_risk(
        self,
        elder_id: str,
        tier: int,
        reason: str,
        created_at: float,
        trace_id: str | None = None,
    ) -> None:
        self.risks.append((elder_id, tier, reason, created_at, trace_id))

    def seed_elder(self, elder_id: str, name: str) -> None:
        self.elders.append((elder_id, name))

    def seed_binding(self, external_id: str, elder_id: str) -> None:
        self.channel_bindings.append((external_id, elder_id))

    def _elder_name_by_id(self, elder_id: str) -> str:
        return next((n for eid, n in self.elders if eid == elder_id), "")

    def _elder_id_by_external(self, external_id: str) -> str:
        return next((eid for ext, eid in self.channel_bindings if ext == external_id), "")

    # --- record 面 ---

    def record_webhook_event(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        event_type: str,
        message_type: str,
        payload: dict,
    ) -> None:
        self.webhook_events.append(
            WebhookEvent(
                self._next_id(),
                trace_id,
                external_id,
                channel,
                event_type,
                message_type,
                payload,
                self.now,
            )
        )

    def record_asr_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        transcript: str,
        source_audio_url: str,
        error_message: str,
    ) -> None:
        self.asr_calls.append(
            AsrCall(
                self._next_id(),
                trace_id,
                external_id,
                channel,
                status,
                latency_ms,
                transcript,
                source_audio_url,
                error_message,
                self.now,
            )
        )

    def record_llm_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        model_name: str,
        input_tokens: int | None,
        output_tokens: int | None,
        content: str,
        error_message: str,
    ) -> None:
        self.llm_calls.append(
            LlmCall(
                self._next_id(),
                trace_id,
                external_id,
                channel,
                status,
                latency_ms,
                model_name,
                input_tokens,
                output_tokens,
                content,
                error_message,
                self.now,
            )
        )

    def record_rag(
        self,
        *,
        trace_id: str,
        elder_id: str,
        query: str,
        index_version: str,
        status: str,
        latency_ms: int,
        safety_level: str,
        reason: str,
        hits: list[dict],
        citations: list[dict],
    ) -> None:
        self.rag_calls.append(
            RagCall(
                self._next_id(),
                trace_id,
                elder_id,
                query,
                index_version,
                status,
                latency_ms,
                safety_level,
                reason,
                hits,
                citations,
                self.now,
            )
        )

    def record_tts_call(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        status: str,
        latency_ms: int,
        content: str,
        error_message: str,
    ) -> None:
        self.tts_calls.append(
            TtsCall(
                self._next_id(),
                trace_id,
                external_id,
                channel,
                status,
                latency_ms,
                content,
                error_message,
                self.now,
            )
        )

    def record_reply(
        self,
        *,
        trace_id: str,
        external_id: str,
        channel: str = "",
        kind: str,
        status: str,
        latency_ms: int,
        round_trip_ms: int | None = None,
        audio_url: str,
    ) -> None:
        self.replies.append(
            Reply(
                self._next_id(),
                trace_id,
                external_id,
                channel,
                kind,
                status,
                latency_ms,
                round_trip_ms,
                audio_url,
                self.now,
            )
        )

    # --- 查詢面 ---

    def get_trace(self, trace_id: str) -> Trace | None:
        webhook_event = next((e for e in self.webhook_events if e.trace_id == trace_id), None)
        asr_call = next((c for c in self.asr_calls if c.trace_id == trace_id), None)
        llm_calls = [c for c in self.llm_calls if c.trace_id == trace_id]
        rag_calls = [c for c in self.rag_calls if c.trace_id == trace_id]
        tts_call = next((c for c in self.tts_calls if c.trace_id == trace_id), None)
        reply = next((r for r in self.replies if r.trace_id == trace_id), None)
        risk_events = [
            TraceRiskEvent(t, reason, ts) for _, t, reason, ts, tid in self.risks if tid == trace_id
        ]
        if not any([webhook_event, asr_call, llm_calls, rag_calls, tts_call, reply, risk_events]):
            return None
        rows_with_source = [webhook_event, asr_call, tts_call, reply, *llm_calls]
        external_id = next((x.external_id for x in rows_with_source if x), "")
        channel = next((x.channel for x in rows_with_source if x), "")
        elder_name = self._elder_name_by_id(self._elder_id_by_external(external_id))
        if not elder_name and rag_calls:
            elder_name = self._elder_name_by_id(rag_calls[0].elder_id)
        return Trace(
            trace_id,
            external_id,
            channel,
            webhook_event,
            asr_call,
            llm_calls,
            rag_calls,
            tts_call,
            reply,
            risk_events,
            elder_name,
        )

    def list_feed(self, *, after: float, before: float | None = None, limit: int) -> list[FeedItem]:
        items: list[FeedItem] = []
        for elder_id, role, content, ts in self.turns:
            if ts > after:
                items.append(
                    FeedItem(
                        "turn",
                        elder_id,
                        self._elder_name_by_id(elder_id),
                        role,
                        content,
                        None,
                        None,
                        ts,
                    )
                )
        for elder_id, _kind, content, ts in self.reminders:
            if ts > after:
                items.append(
                    FeedItem(
                        "reminder",
                        elder_id,
                        self._elder_name_by_id(elder_id),
                        "",
                        content,
                        None,
                        None,
                        ts,
                    )
                )
        for elder_id, tier, reason, ts, tid in self.risks:
            if ts > after:
                items.append(
                    FeedItem(
                        "risk",
                        elder_id,
                        self._elder_name_by_id(elder_id),
                        "",
                        reason,
                        tier,
                        tid,
                        ts,
                    )
                )
        if before is not None:
            items = [i for i in items if i.created_at < before]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def list_timeline_for_elder(
        self, *, elder_id: str, start: float, end: float
    ) -> list[TimelineItem]:
        items: list[TimelineItem] = []
        for eid, role, content, ts in self.turns:
            if eid == elder_id and start <= ts < end:
                items.append(TimelineItem("turn", role, content, None, None, "", ts))
        for eid, _kind, content, ts in self.reminders:
            if eid == elder_id and start <= ts < end:
                items.append(TimelineItem("reminder", "", content, None, None, "", ts))
        for eid, tier, reason, ts, tid in self.risks:
            if eid == elder_id and start <= ts < end:
                items.append(TimelineItem("risk", "", reason, tier, tid, "", ts))
        for c in self.asr_calls:
            if (
                self._elder_id_by_external(c.external_id) == elder_id
                and start <= c.created_at < end
            ):
                items.append(
                    TimelineItem(
                        "voice",
                        "user",
                        c.transcript,
                        None,
                        c.trace_id,
                        c.source_audio_url,
                        c.created_at,
                    )
                )
        for r in self.replies:
            if (
                self._elder_id_by_external(r.external_id) == elder_id
                and r.audio_url
                and start <= r.created_at < end
            ):
                items.append(
                    TimelineItem(
                        "voice", "assistant", "", None, r.trace_id, r.audio_url, r.created_at
                    )
                )
        items.sort(key=lambda i: i.created_at)
        return items

    def list_elders_with_last_active(self) -> list[ElderActivity]:
        result = []
        for elder_id, name in sorted(self.elders, key=lambda e: e[1]):
            actives = [ts for eid, _, _, ts in self.turns if eid == elder_id]
            bound = sorted({"line" for ext, eid in self.channel_bindings if eid == elder_id})
            result.append(
                ElderActivity(elder_id, name, ",".join(bound), max(actives) if actives else None)
            )
        return result

    def get_overview_stats(self, *, today_start: float, hourly_start: float) -> OverviewStats:
        today_turns = [t for t in self.turns if t[3] >= today_start]

        def _nearest_rank(lats: list[int], pct: int) -> float:
            return float(lats[max(0, -(-pct * len(lats) // 100) - 1)]) if lats else 0.0

        def _stage_stats(stage: str, statuses: list[str], lats: list[int]) -> StageStats:
            lats = sorted(lats)
            return StageStats(
                stage,
                len(statuses),
                sum(1 for st in statuses if st != "ok"),
                sum(lats) / len(lats) if lats else 0.0,
                _nearest_rank(lats, 50),
                _nearest_rank(lats, 95),
            )

        stages = []
        for stage, calls in (
            ("asr", self.asr_calls),
            ("llm", self.llm_calls),
            ("tts", self.tts_calls),
        ):
            recent = [c for c in calls if c.created_at >= today_start]
            stages.append(
                _stage_stats(stage, [c.status for c in recent], [c.latency_ms for c in recent])
            )
        # 端到端往返（✅ D-05 戊-2）：round_trip_ms 為 None（未量測）者不計。
        measured = [
            r for r in self.replies if r.created_at >= today_start and r.round_trip_ms is not None
        ]
        stages.append(
            _stage_stats(
                "round_trip", [r.status for r in measured], [r.round_trip_ms for r in measured]
            )
        )
        llm_recent = [c for c in self.llm_calls if c.created_at >= today_start]
        buckets: dict[float, int] = {}
        for t in self.turns:
            if t[3] >= hourly_start:
                bucket = (t[3] // 3600) * 3600
                buckets[bucket] = buckets.get(bucket, 0) + 1
        return OverviewStats(
            turn_count=len(today_turns),
            risk_event_count=sum(1 for r in self.risks if r[3] >= today_start),
            active_elder_count=len({t[0] for t in today_turns}),
            llm_input_tokens=sum(c.input_tokens or 0 for c in llm_recent),
            llm_output_tokens=sum(c.output_tokens or 0 for c in llm_recent),
            stages=stages,
            hourly_turns=[HourlyCount(h, n) for h, n in sorted(buckets.items())],
        )

    def purge_older_than(self, cutoff: float) -> None:
        self.webhook_events = [e for e in self.webhook_events if e.created_at >= cutoff]
        self.asr_calls = [c for c in self.asr_calls if c.created_at >= cutoff]
        self.llm_calls = [c for c in self.llm_calls if c.created_at >= cutoff]
        self.rag_calls = [c for c in self.rag_calls if c.created_at >= cutoff]
        self.tts_calls = [c for c in self.tts_calls if c.created_at >= cutoff]
        self.replies = [r for r in self.replies if r.created_at >= cutoff]
