"""健康報告與每日摘要資源：家屬可見的長輩狀況彙整。

health-report 為聚合計算端點（單數命名）；daily-summaries 為列表資源
（複數 kebab-case）——家屬可看每日摘要、不開放逐字對話（✅ D-09 己-3）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from kinsun.reports.health import build_health_report
from kinsun.reports.reminders import ReminderLogStore
from kinsun.reports.summaries import ConversationSummaryStore
from kinsun.safety.events import RiskEventStore
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


def create_reports_router(
    *,
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
    summaries: ConversationSummaryStore,
    clock: Callable[[], datetime],
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
) -> APIRouter:
    router = APIRouter(tags=["reports"])

    @router.get("/elders/{elder_id}/health-report")
    def health_report(
        elder_id: str,
        window_days: int = Query(default=30, ge=1, le=90),
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        """window_days 開放查詢參數（✅ 庚-40／A-36）：預設近 30 天、上限 90。"""
        scope.assert_manages(auth, elder_id)
        report = build_health_report(
            elder_id=elder_id,
            risk_events=risk_events,
            reminder_logs=reminder_logs,
            now=clock(),
            window_days=window_days,
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

    @router.get("/elders/{elder_id}/daily-summaries")
    def daily_summaries(
        elder_id: str,
        limit: int = Query(default=30, ge=1, le=90),
        auth: GuardianAuth = Depends(current_guardian),
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        rows = summaries.list_for_elder(elder_id)[:limit]
        return ok(
            [{"date": s.date, "content": s.content, "created_at": s.created_at} for s in rows],
            meta={"limit": limit},
        )

    return router
