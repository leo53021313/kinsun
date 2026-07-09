"""App 內通知資源（✅ D-12，甲-6）：家屬拉取自己的警報／提醒／關懷訊息。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from kinsun.accounts.service import AccountService
from kinsun.notifications.store import AppNotificationStore
from kinsun.web.envelope import ok


def create_notifications_router(
    *,
    accounts: AccountService,
    notifications: AppNotificationStore | None,
    current_app_guardian: Callable[..., str],
) -> APIRouter:
    router = APIRouter(tags=["notifications"])

    @router.get("/notifications")
    def list_app_notifications(guardian_id: str = Depends(current_app_guardian)) -> dict:
        """最近先；未讀判斷由 App 端以本機時間戳處理。"""
        if notifications is None:
            return ok([])
        external_ids = accounts.app_external_ids_of_guardian(guardian_id)
        items = notifications.list_for_external_ids(external_ids) if external_ids else []
        return ok([{"content": n.content, "created_at": n.created_at} for n in items])

    return router
