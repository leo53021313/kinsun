"""把 App 內通知同步推到使用者的裝置（真推播 D-08 階段 5，2026-07-29）。

放在 `AppOutboundChannel` 與 `ExpoPushClient` 中間的一層：出站 adapter 只知道
通道帳號 `external_id`，推播 token 卻是掛在「人」身上（一人可多台裝置），
中間這段反查與扇出邏輯不屬於任何一邊。

⚠️ 推播**永遠不可讓落庫失敗**。App 內通知是唯一保證留存的路徑（App 沒開、
token 失效、換手機時推播必然推不到），推播只是「順便讓手機響一下」。因此
`AppOutboundChannel` 先寫 `app_notifications`、再呼叫這裡，且這裡的任何例外
都由呼叫端吞掉。
"""

from __future__ import annotations

import logging

from kinsun.accounts.models import Channel
from kinsun.accounts.service import AccountService
from kinsun.notifications.expo_push import ExpoPushClient
from kinsun.notifications.push_tokens import PushTokenStore

logger = logging.getLogger("kinsun.push")

# 推播標題固定用產品名：長輩看到的是鎖定畫面上的一行，標題要能一眼認出是誰。
PUSH_TITLE = "金孫"


class PushDelivery:
    def __init__(
        self, accounts: AccountService, tokens: PushTokenStore, client: ExpoPushClient
    ) -> None:
        self._accounts = accounts
        self._tokens = tokens
        self._client = client

    def push(self, external_id: str, text: str) -> None:
        """對該通道帳號的主人所有裝置送一則推播。無裝置登記時直接返回。"""
        resolved = self._accounts.bound_principal(Channel.APP, external_id)
        if resolved is None:
            return
        principal_type, principal_id = resolved
        rows = self._tokens.list_for_principal(principal_type, principal_id)
        if not rows:
            return
        outcome = self._client.send([r.token for r in rows], PUSH_TITLE, text)
        # 死 token 立刻清掉：留著只會讓之後每次派送都白打一次，且把失敗數灌水到
        # 看不出真正的問題。清不掉不影響本次推播結果。
        for token in outcome.dead_tokens:
            try:
                self._tokens.remove(token)
            except Exception:  # noqa: BLE001 - 清理失敗不可中斷派送
                logger.warning("清除失效推播 token 失敗")
