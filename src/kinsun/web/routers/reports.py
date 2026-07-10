"""健康報告資源：近 30 天危急事件＋提醒紀錄彙整（聚合計算端點，單數命名）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends

from kinsun.reports.health import build_health_report
from kinsun.reports.reminders import ReminderLogStore
from kinsun.safety.events import RiskEventStore
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


def create_reports_router(
    *,
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
    clock: Callable[[], datetime],
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
) -> APIRouter:
    router = APIRouter(tags=["reports"])

    @router.get("/elders/{elder_id}/health-report")
    def health_report(elder_id: str, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        scope.assert_manages(auth, elder_id)
        report = build_health_report(
            elder_id=elder_id,
            risk_events=risk_events,
            reminder_logs=reminder_logs,
            now=clock(),
        )
        return ok(
            {
                "risk_events": [
                    {"tier": int(e.tier), "reason": e.reason, "created_at": e.created_at}
                    for e in report.risks
                ],
                "reminders": [
                    {"kind": r.kind, "content": r.content, "created_at": r.created_at}
                    for r in report.reminders
                ],
            }
        )

    return router
