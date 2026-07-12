"""REST 路由套件（✅ D-28，乙-4）：一資源一檔，prefix 由組裝處（app.py）統一指定。

三個聚合工廠對應三個認證面：
- `create_guardian_face_router`：家屬面（App token／LIFF idToken 雙認證）
- `create_app_auth_router`：App 帳號與通知（註冊／登入／裝置綁定／通知）
- `create_admin_router`：觀測後台（X-Admin-Key）

對講機回合（turns）為通道層邏輯，留在 `channels/app/turns.py`，不入本套件。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter

from kinsun.accounts.service import AccountService
from kinsun.appointments.service import AppointmentService
from kinsun.medications.service import MedicationService
from kinsun.notifications.store import AppNotificationStore
from kinsun.reports.reminders import ReminderLogStore
from kinsun.reports.summaries import ConversationSummaryStore
from kinsun.safety.events import RiskEventStore
from kinsun.web.auth import LiffVerifier
from kinsun.web.ratelimit import SlidingWindowRateLimiter
from kinsun.web.routers.admin import create_admin_router
from kinsun.web.routers.appointments import create_appointments_router
from kinsun.web.routers.deps import (
    GuardianScope,
    build_current_app_guardian,
    build_current_guardian,
)
from kinsun.web.routers.device_bindings import create_device_bindings_router
from kinsun.web.routers.elders import create_elders_router
from kinsun.web.routers.guardians import create_guardians_router
from kinsun.web.routers.medications import create_medications_router
from kinsun.web.routers.meta import create_meta_router
from kinsun.web.routers.notifications import create_notifications_router
from kinsun.web.routers.reports import create_reports_router
from kinsun.web.routers.sessions import create_sessions_router

__all__ = [
    "create_admin_router",
    "create_app_auth_router",
    "create_guardian_face_router",
    "create_meta_router",
]


def create_guardian_face_router(
    *,
    verifier: LiffVerifier,
    accounts: AccountService,
    medications: MedicationService,
    appointments: AppointmentService,
    clock: Callable[[], datetime],
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
    summaries: ConversationSummaryStore,
) -> APIRouter:
    """家屬面聚合：長輩／用藥／回診／健康報告／每日摘要，共用雙認證與可及範圍守門。"""
    current_guardian = build_current_guardian(verifier, accounts)
    scope = GuardianScope(accounts)
    router = APIRouter()
    router.include_router(
        create_elders_router(accounts=accounts, current_guardian=current_guardian, scope=scope)
    )
    router.include_router(
        create_medications_router(
            medications=medications, current_guardian=current_guardian, scope=scope
        )
    )
    router.include_router(
        create_appointments_router(
            appointments=appointments, clock=clock, current_guardian=current_guardian, scope=scope
        )
    )
    router.include_router(
        create_reports_router(
            risk_events=risk_events,
            reminder_logs=reminder_logs,
            summaries=summaries,
            clock=clock,
            current_guardian=current_guardian,
            scope=scope,
        )
    )
    return router


def create_app_auth_router(
    *,
    accounts: AccountService,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    notifications: AppNotificationStore | None = None,
) -> APIRouter:
    """App 帳號面聚合：註冊／登入／裝置綁定共用同一節流器（各端點獨立計數）。"""
    limiter = rate_limiter or SlidingWindowRateLimiter(10, 300.0)
    current_app_guardian = build_current_app_guardian(accounts)
    router = APIRouter()
    router.include_router(create_guardians_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(create_sessions_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(create_device_bindings_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(
        create_notifications_router(
            accounts=accounts,
            notifications=notifications,
            current_app_guardian=current_app_guardian,
        )
    )
    return router
