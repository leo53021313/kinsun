"""開發團隊觀測後台 REST API（唯讀）：共用金鑰驗證，供 /admin 前端查詢。"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from kinsun.observability.models import (
    ElderActivity,
    FeedItem,
    OverviewStats,
    TimelineItem,
    Trace,
)
from kinsun.observability.store import TraceStore
from kinsun.safety.events import RiskEventStore

# 分級器故障告警（✅ D-31＋D-66 admin 半邊）：近 60 分鐘 fail-safe 留痕事件達門檻即回告警。
# 門檻與視窗暫為常數；隨丙-6（危急門檻 env 化）一併調整。
FAILSAFE_ALERT_WINDOW_MINUTES = 60
FAILSAFE_ALERT_THRESHOLD = 3


def create_admin_api_router(
    *,
    admin_api_key: str,
    traces: TraceStore,
    clock: Callable[[], datetime],
    risk_events: RiskEventStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def require_admin(x_admin_key: str = Header(default="", alias="X-Admin-Key")) -> None:
        if not admin_api_key:
            raise HTTPException(status_code=503, detail="admin api disabled")
        if not hmac.compare_digest(x_admin_key.encode(), admin_api_key.encode()):
            raise HTTPException(status_code=401, detail="invalid admin key")

    def _today_start() -> float:
        now = clock()
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _alerts(now: datetime) -> list[dict]:
        if risk_events is None:
            return []
        cutoff = (now - timedelta(minutes=FAILSAFE_ALERT_WINDOW_MINUTES)).timestamp()
        n = risk_events.count_failsafe_since(cutoff)
        if n < FAILSAFE_ALERT_THRESHOLD:
            return []
        return [
            {
                "kind": "risk_classifier_failure",
                "count": n,
                "window_minutes": FAILSAFE_ALERT_WINDOW_MINUTES,
            }
        ]

    @router.get("/overview", dependencies=[Depends(require_admin)])
    def overview() -> dict:
        now = clock()
        stats = traces.get_overview_stats(
            today_start=_today_start(),
            hourly_start=(now - timedelta(hours=24)).timestamp(),
        )
        return {**_overview_json(stats, generated_at=now.timestamp()), "alerts": _alerts(now)}

    @router.get("/elders", dependencies=[Depends(require_admin)])
    def list_elders() -> dict:
        return {"elders": [_elder_json(e) for e in traces.list_elders_with_last_active()]}

    def _find_elder(elder_id: str) -> ElderActivity:
        elder = next(
            (e for e in traces.list_elders_with_last_active() if e.elder_id == elder_id),
            None,
        )
        if elder is None:
            raise HTTPException(status_code=404, detail="elder not found")
        return elder

    @router.get("/messages", dependencies=[Depends(require_admin)])
    def list_messages(
        after: float = Query(default=0.0, ge=0.0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return {"messages": [_feed_json(m) for m in traces.list_feed(after=after, limit=limit)]}

    @router.get("/elders/{elder_id}/timeline", dependencies=[Depends(require_admin)])
    def elder_timeline(elder_id: str, date: str = Query(default="")) -> dict:
        elder = _find_elder(elder_id)  # 404 守門
        if date:
            try:
                day = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid date") from exc
        else:
            day = clock().date()
        # 台灣無日光節約時間，一天固定 86400 秒。
        start = datetime(day.year, day.month, day.day, tzinfo=clock().tzinfo).timestamp()
        items = traces.list_timeline_for_elder(
            elder_id=elder_id,
            start=start,
            end=start + 86400.0,
        )
        return {
            "elder_id": elder.elder_id,
            "name": elder.name,
            "date": day.isoformat(),
            "items": [_timeline_json(i) for i in items],
        }

    @router.get("/traces/{trace_id}", dependencies=[Depends(require_admin)])
    def trace_detail(trace_id: str) -> dict:
        trace = traces.get_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return _trace_json(trace)

    return router


def _overview_json(stats: OverviewStats, *, generated_at: float) -> dict:
    return {
        "generated_at": generated_at,
        "turn_count": stats.turn_count,
        "risk_event_count": stats.risk_event_count,
        "active_elder_count": stats.active_elder_count,
        "llm_input_tokens": stats.llm_input_tokens,
        "llm_output_tokens": stats.llm_output_tokens,
        "stages": [
            {
                "stage": s.stage,
                "call_count": s.call_count,
                "error_count": s.error_count,
                "avg_latency_ms": s.avg_latency_ms,
                "p95_latency_ms": s.p95_latency_ms,
            }
            for s in stats.stages
        ],
        "hourly_turns": [
            {"hour_start": h.hour_start, "turn_count": h.turn_count} for h in stats.hourly_turns
        ],
    }


def _elder_json(e: ElderActivity) -> dict:
    return {
        "elder_id": e.elder_id,
        "name": e.name,
        "bound_channels": e.bound_channels,
        "last_active_at": e.last_active_at,
    }


def _feed_json(m: FeedItem) -> dict:
    return {
        "kind": m.kind,
        "elder_id": m.elder_id,
        "elder_name": m.elder_name,
        "role": m.role,
        "content": m.content,
        "tier": m.tier,
        "trace_id": m.trace_id,
        "created_at": m.created_at,
    }


def _timeline_json(i: TimelineItem) -> dict:
    return {
        "kind": i.kind,
        "role": i.role,
        "content": i.content,
        "tier": i.tier,
        "trace_id": i.trace_id,
        "audio_url": i.audio_url,
        "created_at": i.created_at,
    }


def _trace_json(t: Trace) -> dict:
    return {
        "trace_id": t.trace_id,
        "line_user_id": t.line_user_id,
        "elder_name": t.elder_name,
        "webhook_event": None
        if t.webhook_event is None
        else {
            "event_type": t.webhook_event.event_type,
            "message_type": t.webhook_event.message_type,
            "payload": t.webhook_event.payload,
            "created_at": t.webhook_event.created_at,
        },
        "asr_call": None
        if t.asr_call is None
        else {
            "status": t.asr_call.status,
            "latency_ms": t.asr_call.latency_ms,
            "transcript": t.asr_call.transcript,
            "source_audio_url": t.asr_call.source_audio_url,
            "error_message": t.asr_call.error_message,
            "created_at": t.asr_call.created_at,
        },
        "llm_calls": [
            {
                "status": c.status,
                "latency_ms": c.latency_ms,
                "model_name": c.model_name,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "content": c.content,
                "error_message": c.error_message,
                "created_at": c.created_at,
            }
            for c in t.llm_calls
        ],
        "tts_call": None
        if t.tts_call is None
        else {
            "status": t.tts_call.status,
            "latency_ms": t.tts_call.latency_ms,
            "content": t.tts_call.content,
            "error_message": t.tts_call.error_message,
            "created_at": t.tts_call.created_at,
        },
        "reply": None
        if t.reply is None
        else {
            "kind": t.reply.kind,
            "status": t.reply.status,
            "latency_ms": t.reply.latency_ms,
            "audio_url": t.reply.audio_url,
            "created_at": t.reply.created_at,
        },
        "risk_events": [
            {"tier": r.tier, "reason": r.reason, "created_at": r.created_at} for r in t.risk_events
        ],
    }
