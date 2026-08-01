"""App 內通知資源（✅ D-12，甲-6）：家屬與長輩各拉取寫給自己的訊息。

長輩面（X-01，2026-07-29）：提醒送出＝`AppOutboundChannel` 落一筆 `app_notifications`，
但先前只有家屬讀得到、且只查家屬自己的 `external_id`——寫給長輩的那一列誰都讀不到，
用藥／回診／主動關懷對純 App 家庭等於不存在。這裡補上長輩自己的讀取路徑。
（真推播 D-08 階段 5 到位後，本端點仍是推不到時的補拉路徑，不會被取代。）
"""

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
    current_app_elder: Callable[..., str],
) -> APIRouter:
    router = APIRouter(tags=["notifications"])

    def _items(external_ids: list[str]) -> dict:
        if notifications is None or not external_ids:
            return ok([])
        items = notifications.list_for_external_ids(external_ids)
        # severity（2026-08-01）：讓前端分得出「跌倒了」與「該吃藥了」。鍵名與
        # kinsun-shared/types.ts::AppNotification 完全一致（snake_case，前後端同名）。
        # 值一律是 `notice`／`alert` 的字面值——`severity_from_db` 已在 store 層
        # 把認不得的舊值收斂掉，這裡不會漏出 enum 物件或非預期字串。
        return ok(
            [
                {
                    "content": n.content,
                    "created_at": n.created_at,
                    "severity": n.severity.value,
                }
                for n in items
            ]
        )

    @router.get("/notifications")
    def list_app_notifications(guardian_id: str = Depends(current_app_guardian)) -> dict:
        """家屬面：最近先；未讀判斷由 App 端以本機時間戳處理。"""
        return _items(accounts.app_external_ids_of_guardian(guardian_id))

    @router.get("/elder-notifications")
    def list_elder_notifications(elder_id: str = Depends(current_app_elder)) -> dict:
        """長輩面：只回寫給本人的訊息（用藥／回診提醒、主動關懷）。

        無 App 綁定時 `app_external_id_of_elder` 回 None → 空陣列，不是錯誤：
        長輩剛建檔尚未配對時本來就沒有任何訊息。
        """
        external_id = accounts.app_external_id_of_elder(elder_id)
        return _items([external_id] if external_id else [])

    return router
