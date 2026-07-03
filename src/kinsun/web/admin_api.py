"""開發團隊觀測後台 REST API（唯讀）：共用金鑰驗證，供 /admin 前端查詢。"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException

from kinsun.observability.models import ElderActivity, OverviewStats
from kinsun.observability.store import TraceStore


def create_admin_api_router(
    *,
    admin_api_key: str,
    traces: TraceStore,
    clock: Callable[[], datetime],
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

    @router.get("/overview", dependencies=[Depends(require_admin)])
    def overview() -> dict:
        now = clock()
        stats = traces.get_overview_stats(
            today_start=_today_start(),
            hourly_start=(now - timedelta(hours=24)).timestamp(),
        )
        return _overview_json(stats, generated_at=now.timestamp())

    @router.get("/elders", dependencies=[Depends(require_admin)])
    def list_elders() -> dict:
        return {"elders": [_elder_json(e) for e in traces.list_elders_with_last_active()]}

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
        "line_user_id": e.line_user_id,
        "last_active_at": e.last_active_at,
    }
