"""裝置推播 token 註冊（真推播 D-08 階段 5，2026-07-29）。

長輩與家屬**共用同一支端點**：兩邊都要收推播（長輩收用藥提醒、家屬收危急警報），
差別只在 token 綁到哪個主體，而那由 Authorization 決定，不由呼叫端宣告——
讓客戶端自報身分等於開一個「把別人的提醒導到我手機」的破口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from kinsun.accounts.models import PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.notifications.push_tokens import PushTokenStore
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode

# 平台白名單：值只進 DB 供排查，不參與路由決策（Expo 兩邊都吃同一支 API）。
_PLATFORMS = frozenset({"android", "ios"})


class PushTokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    platform: str = Field(min_length=1, max_length=16)


def create_push_tokens_router(
    *,
    accounts: AccountService,
    push_tokens: PushTokenStore | None,
) -> APIRouter:
    router = APIRouter(tags=["push"])

    def _principal(authorization: str = Header(default="")) -> tuple[PrincipalType, str]:
        """長輩或家屬皆可；主體由 token 決定，不看請求內容。"""
        raw = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(raw) if raw else None
        if auth is None:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        return auth.principal_type, auth.principal_id

    @router.post("/push-tokens", status_code=201)
    def register_push_token(
        body: PushTokenIn,
        principal: tuple[PrincipalType, str] = Depends(_principal),
    ) -> dict:
        """登記這台裝置。同一個 token 再打一次＝更新（換人用同一台就改綁）。"""
        platform = body.platform.strip().lower()
        if platform not in _PLATFORMS:
            raise HTTPException(status_code=400, detail=ErrorCode.VALIDATION_ERROR)
        if push_tokens is None:
            # 未配置推播的部署：收下但不存，回 201 讓 App 不必分辨伺服器版本。
            return ok({"registered": False})
        principal_type, principal_id = principal
        push_tokens.save(body.token.strip(), principal_type, principal_id, platform)
        return ok({"registered": True})

    @router.delete("/push-tokens/{token}", status_code=204)
    def remove_push_token(
        token: str,
        principal: tuple[PrincipalType, str] = Depends(_principal),
    ) -> None:
        """登出時清掉，避免提醒繼續推到已經不是本人在用的裝置。

        只刪自己名下的：否則知道別人 token 的人可以讓對方從此收不到提醒。
        """
        if push_tokens is None:
            return None
        principal_type, principal_id = principal
        owned = {r.token for r in push_tokens.list_for_principal(principal_type, principal_id)}
        if token in owned:
            push_tokens.remove(token)
        return None

    return router
