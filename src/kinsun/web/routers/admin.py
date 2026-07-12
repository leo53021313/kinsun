"""觀測後台資源（唯讀）：共用金鑰驗證，供 /admin 前端查詢。"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from kinsun.accounts.models import PrincipalType
from kinsun.accounts.store import AccountStore
from kinsun.appointments.store import AppointmentStore
from kinsun.medications.store import MedicationStore
from kinsun.memory.longterm.store import LongTermStore
from kinsun.observability.models import (
    ElderActivity,
    FeedItem,
    OverviewStats,
    TimelineItem,
    Trace,
)
from kinsun.observability.store import TraceStore
from kinsun.reports.reminders import ReminderLogStore
from kinsun.reports.summaries import ConversationSummaryStore
from kinsun.safety.deliveries import RiskNotificationLogStore
from kinsun.safety.events import RiskEventStore
from kinsun.web.envelope import ok

# 分級器故障告警（✅ D-31＋D-66 admin 半邊）：近 60 分鐘 fail-safe 留痕事件達門檻即回告警。
# 門檻與視窗暫為常數；隨丙-6（危急門檻 env 化）一併調整。
FAILSAFE_ALERT_WINDOW_MINUTES = 60
FAILSAFE_ALERT_THRESHOLD = 3

# 家屬通知送失敗告警（✅ 庚-02／A-40）：家屬漏收危急警報＝最嚴重產品失敗，
# 一筆送失敗即告警（門檻 1，不設容忍噪音的緩衝）。
DELIVERY_FAILURE_ALERT_WINDOW_MINUTES = 60
DELIVERY_FAILURE_ALERT_THRESHOLD = 1


def build_require_admin(admin_api_key: str) -> Callable:
    """X-Admin-Key 守門（admin.py 與 admin_jobs.py 共用）。"""

    def require_admin(x_admin_key: str = Header(default="", alias="X-Admin-Key")) -> None:
        if not admin_api_key:
            raise HTTPException(status_code=503, detail="admin_disabled")
        if not hmac.compare_digest(x_admin_key.encode(), admin_api_key.encode()):
            raise HTTPException(status_code=401, detail="invalid_admin_key")

    return require_admin


def create_admin_router(
    *,
    admin_api_key: str,
    traces: TraceStore,
    clock: Callable[[], datetime],
    risk_events: RiskEventStore | None = None,
    account_store: AccountStore,
    med_store: MedicationStore,
    appt_store: AppointmentStore,
    reminder_logs: ReminderLogStore,
    summaries: ConversationSummaryStore,
    long_term: LongTermStore,
    deliveries: RiskNotificationLogStore,
) -> APIRouter:
    router = APIRouter(tags=["admin"])
    require_admin = build_require_admin(admin_api_key)

    def _today_start() -> float:
        now = clock()
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _alerts(now: datetime) -> list[dict]:
        alerts: list[dict] = []
        if risk_events is not None:
            cutoff = (now - timedelta(minutes=FAILSAFE_ALERT_WINDOW_MINUTES)).timestamp()
            n = risk_events.count_failsafe_since(cutoff)
            if n >= FAILSAFE_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "kind": "risk_classifier_failure",
                        "count": n,
                        "window_minutes": FAILSAFE_ALERT_WINDOW_MINUTES,
                    }
                )
        d_cutoff = (now - timedelta(minutes=DELIVERY_FAILURE_ALERT_WINDOW_MINUTES)).timestamp()
        failed = deliveries.count_failed_since(d_cutoff)
        if failed >= DELIVERY_FAILURE_ALERT_THRESHOLD:
            alerts.append(
                {
                    "kind": "guardian_notification_failure",
                    "count": failed,
                    "window_minutes": DELIVERY_FAILURE_ALERT_WINDOW_MINUTES,
                }
            )
        return alerts

    @router.get("/overview", dependencies=[Depends(require_admin)])
    def overview() -> dict:
        now = clock()
        stats = traces.get_overview_stats(
            today_start=_today_start(),
            hourly_start=(now - timedelta(hours=24)).timestamp(),
        )
        return ok({**_overview_json(stats, generated_at=now.timestamp()), "alerts": _alerts(now)})

    @router.get("/elders", dependencies=[Depends(require_admin)])
    def list_elders() -> dict:
        return ok([_elder_json(e) for e in traces.list_elders_with_last_active()])

    def _find_elder(elder_id: str) -> ElderActivity:
        elder = next(
            (e for e in traces.list_elders_with_last_active() if e.elder_id == elder_id),
            None,
        )
        if elder is None:
            raise HTTPException(status_code=404, detail="elder_not_found")
        return elder

    @router.get("/messages", dependencies=[Depends(require_admin)])
    def list_messages(
        after: float = Query(default=0.0, ge=0.0),
        before: float | None = Query(default=None, ge=0.0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        """游標分頁（✅ D-29 乙-6）：after 取更新、before 回翻歷史；游標值＝created_at。"""
        items = traces.list_feed(after=after, before=before, limit=limit + 1)
        has_more = len(items) > limit
        items = items[:limit]
        return ok(
            [_feed_json(m) for m in items],
            meta={
                "limit": limit,
                "before": before,
                "after": after or None,
                "has_more": has_more,
            },
        )

    @router.get("/elders/{elder_id}/timeline", dependencies=[Depends(require_admin)])
    def elder_timeline(elder_id: str, date: str = Query(default="")) -> dict:
        elder = _find_elder(elder_id)  # 404 守門
        if date:
            try:
                day = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid_date") from exc
        else:
            day = clock().date()
        # 台灣無日光節約時間，一天固定 86400 秒。
        start = datetime(day.year, day.month, day.day, tzinfo=clock().tzinfo).timestamp()
        items = traces.list_timeline_for_elder(
            elder_id=elder_id,
            start=start,
            end=start + 86400.0,
        )
        return ok(
            {
                "elder_id": elder.elder_id,
                "name": elder.name,
                "date": day.isoformat(),
                "items": [_timeline_json(i) for i in items],
            }
        )

    @router.get("/traces/{trace_id}", dependencies=[Depends(require_admin)])
    def trace_detail(trace_id: str) -> dict:
        trace = traces.get_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace_not_found")
        return ok(_trace_json(trace))

    # --- 長輩詳情分頁（spec 2026-07-12 §3.3）：以 elder_id 主鍵直查，與時間軸的
    # _find_elder（掃活動清單）分工——這幾頁不依賴長輩曾有對話。 ---

    def _require_elder(elder_id: str) -> None:
        if account_store.get_elder(elder_id) is None:
            raise HTTPException(status_code=404, detail="elder_not_found")

    @router.get("/elders/{elder_id}/reminders", dependencies=[Depends(require_admin)])
    def elder_reminders(elder_id: str) -> dict:
        _require_elder(elder_id)
        return ok(
            {
                "medications": [
                    {
                        "medication_id": m.medication_id,
                        "name": m.name,
                        "slots": [s.value for s in m.slots],
                    }
                    for m in med_store.list_for_elder(elder_id)
                ],
                "appointments": [
                    {
                        "appointment_id": a.appointment_id,
                        "date": a.date,
                        "label": a.label,
                        "time": a.time,
                    }
                    for a in appt_store.list_for_elder(elder_id)
                ],
                "reminder_logs": [
                    {"kind": log.kind, "content": log.content, "created_at": log.created_at}
                    for log in reminder_logs.list_for_elder(elder_id)[:50]
                ],
            }
        )

    @router.get("/elders/{elder_id}/memory", dependencies=[Depends(require_admin)])
    def elder_memory(elder_id: str) -> dict:
        _require_elder(elder_id)
        return ok(
            {
                "memories": [
                    {"text": m.text, "provenance": m.provenance, "date": m.date}
                    for m in long_term.list_for_elder(elder_id)
                ],
                "summaries": [
                    {"date": s.date, "content": s.content, "created_at": s.created_at}
                    for s in summaries.list_for_elder(elder_id)[:30]
                ],
            }
        )

    @router.get("/elders/{elder_id}/account", dependencies=[Depends(require_admin)])
    def elder_account(elder_id: str) -> dict:
        _require_elder(elder_id)
        now = clock().timestamp()

        def invite_status(invite) -> str:
            if invite.used_at is not None:
                return "used"
            if invite.attempts >= invite.max_attempts:
                return "locked"
            if invite.expires_at < now:
                return "expired"
            return "active"

        account = account_store.get_elder_account(elder_id)
        consent = account_store.get_consent(elder_id)
        return ok(
            {
                "bindings": [
                    {
                        "channel": b.channel.value,
                        "external_id": b.external_id,
                        "created_at": b.created_at,
                    }
                    for b in account_store.list_channel_bindings_for_principal(
                        PrincipalType.ELDER, elder_id
                    )
                ],
                "invites": [
                    {
                        "code": i.code,
                        "role": i.role.value,
                        "status": invite_status(i),
                        "expires_at": i.expires_at,
                        "attempts": i.attempts,
                    }
                    for i in account_store.list_invites_for_elder(elder_id)
                ],
                "consent": None
                if consent is None
                else {
                    "consent_by": consent.consent_by.value,
                    "version": consent.version,
                    "granted_at": consent.granted_at,
                    "revoked_at": consent.revoked_at,
                },
                "has_password_account": account is not None,
                "phone": account.phone if account else None,
                # token 只回概況（建立時間）；DB 僅存雜湊，雜湊本身也不外洩。
                "tokens": [
                    {"created_at": t.created_at}
                    for t in account_store.list_api_tokens_for_principal(
                        PrincipalType.ELDER, elder_id
                    )
                ],
                "guardians": [
                    {
                        "guardian_id": eg.guardian_id,
                        "name": g.name
                        if (g := account_store.get_guardian(eg.guardian_id))
                        else eg.guardian_id,
                        "role": eg.role.value,
                        "escalation_order": eg.escalation_order,
                    }
                    for eg in account_store.list_elder_guardians(elder_id)
                ],
            }
        )

    @router.get("/elders/{elder_id}/risk-notifications", dependencies=[Depends(require_admin)])
    def elder_risk_notifications(elder_id: str) -> dict:
        _require_elder(elder_id)
        return ok(
            [
                {
                    "guardian_id": d.guardian_id,
                    "guardian_name": g.name
                    if (g := account_store.get_guardian(d.guardian_id))
                    else d.guardian_id,
                    "tier": int(d.tier),
                    "delivered": d.delivered,
                    "channels": d.channels,
                    "created_at": d.created_at,
                }
                for d in deliveries.list_for_elder(elder_id)[:100]
            ]
        )

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
                "p50_latency_ms": s.p50_latency_ms,
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
        "external_id": t.external_id,
        "channel": t.channel,
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
            "round_trip_ms": t.reply.round_trip_ms,
            "audio_url": t.reply.audio_url,
            "created_at": t.reply.created_at,
        },
        "risk_events": [
            {"tier": r.tier, "reason": r.reason, "created_at": r.created_at} for r in t.risk_events
        ],
    }
