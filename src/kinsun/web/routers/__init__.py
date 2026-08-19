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
from kinsun.notifications.push_tokens import PushTokenStore
from kinsun.notifications.store import AppNotificationStore
from kinsun.reports.reminders import ReminderLogStore
from kinsun.reports.summaries import ConversationSummaryStore
from kinsun.safety.events import RiskEventStore
from kinsun.schedules.service import ScheduleService
from kinsun.voice_profiles.store import VoiceProfileStore
from kinsun.web.auth import LiffVerifier
from kinsun.web.ratelimit import RateLimiter, SlidingWindowRateLimiter
from kinsun.web.routers.admin import create_admin_router
from kinsun.web.routers.admin_jobs import create_admin_jobs_router
from kinsun.web.routers.admin_strategies import create_admin_strategies_router
from kinsun.web.routers.deps import (
    GuardianScope,
    build_current_app_elder,
    build_current_app_guardian,
    build_current_guardian,
)
from kinsun.web.routers.device_bindings import create_device_bindings_router
from kinsun.web.routers.elders import create_elders_router
from kinsun.web.routers.guardians import create_guardians_router
from kinsun.web.routers.meta import create_meta_router
from kinsun.web.routers.notifications import create_notifications_router
from kinsun.web.routers.push_tokens import create_push_tokens_router
from kinsun.web.routers.reports import create_reports_router
from kinsun.web.routers.schedules import create_schedules_router
from kinsun.web.routers.sessions import create_sessions_router
from kinsun.web.routers.voice_profiles import create_voice_profiles_router

__all__ = [
    "create_admin_jobs_router",
    "create_admin_router",
    "create_admin_strategies_router",
    "create_app_auth_router",
    "create_guardian_face_router",
    "create_meta_router",
]


def create_guardian_face_router(
    *,
    verifier: LiffVerifier,
    accounts: AccountService,
    schedules: ScheduleService,
    clock: Callable[[], datetime],
    risk_events: RiskEventStore,
    reminder_logs: ReminderLogStore,
    summaries: ConversationSummaryStore,
    appointment_hour: int,
    voice_profiles: VoiceProfileStore | None = None,
    publisher=None,
    ack_audio=None,
) -> APIRouter:
    """家屬面聚合：長輩／排程／健康報告／每日摘要，共用雙認證與可及範圍守門。

    用藥與回診自 D-76 P3 起併入 schedules 單一資源，不再各有一支 router。

    `appointment_hour` 沒有預設值是刻意的：它必須與 LINE 選單（`ScheduleMenu`）拿的
    是同一個 `APPOINTMENT_REMINDER_HOUR`，給了預設值就等於留一條會靜靜漂移的路——
    而漂移的後果要等到那個時刻沒響才會發現。
    """
    current_guardian = build_current_guardian(verifier, accounts)
    scope = GuardianScope(accounts)
    router = APIRouter()
    router.include_router(
        create_elders_router(accounts=accounts, current_guardian=current_guardian, scope=scope)
    )
    router.include_router(
        create_voice_profiles_router(
            voice_profiles=voice_profiles,
            publisher=publisher,
            current_guardian=current_guardian,
            scope=scope,
            clock=clock,
            # 家屬錄完克隆聲音當下就以新聲音預錄安撫話（2026-08-19），
            # 不必等長輩第一次開口。None＝功能未啟用時照舊。
            ack_audio=ack_audio,
        )
    )
    router.include_router(
        create_schedules_router(
            schedules=schedules,
            current_guardian=current_guardian,
            scope=scope,
            clock=clock,
            appointment_hour=appointment_hour,
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
    rate_limiter: RateLimiter | None = None,
    notifications: AppNotificationStore | None = None,
    push_tokens: PushTokenStore | None = None,
) -> APIRouter:
    """App 帳號面聚合：註冊／登入／裝置綁定共用同一節流器（各端點獨立計數）。"""
    limiter = rate_limiter or SlidingWindowRateLimiter(10, 300.0)
    current_app_guardian = build_current_app_guardian(accounts)
    current_app_elder = build_current_app_elder(accounts)
    router = APIRouter()
    router.include_router(create_guardians_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(create_sessions_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(create_device_bindings_router(accounts=accounts, rate_limiter=limiter))
    router.include_router(
        create_notifications_router(
            accounts=accounts,
            notifications=notifications,
            current_app_guardian=current_app_guardian,
            current_app_elder=current_app_elder,
        )
    )
    router.include_router(create_push_tokens_router(accounts=accounts, push_tokens=push_tokens))
    return router
