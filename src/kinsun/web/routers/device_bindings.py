"""長輩裝置綁定資源：綁定碼換 App 通道綁定＋裝置 token（PROXY 同意留痕）。

⚠ D-71：長輩帳密註冊／登入端點於己-6 增補（家屬代辦建帳、長輩機登入一次）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.models import ConsentBy
from kinsun.accounts.service import AccountService, InviteError
from kinsun.web.envelope import ok
from kinsun.web.ratelimit import SlidingWindowRateLimiter, throttle_or_429

# 邀請碼錯誤 → (HTTP, 標準錯誤碼)：查無 404，其餘為「碼已不可用」的衝突（✅ D-24）。
_INVITE_STATUS = {
    "not_found": (404, "invite_not_found"),
    "used": (409, "invite_used"),
    "expired": (409, "invite_expired"),
    "too_many_attempts": (409, "too_many_attempts"),
}


class DeviceBindingIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)


def create_device_bindings_router(
    *, accounts: AccountService, rate_limiter: SlidingWindowRateLimiter
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/device-bindings", status_code=201)
    def create_device_binding(body: DeviceBindingIn, request: Request) -> dict:
        throttle_or_429(rate_limiter, "bind", request)
        try:
            # App 端綁定碼由家屬產生、多半由家屬替長輩操作 → 同意主體記 PROXY。
            elder, token = accounts.bind_elder_device(body.code, consent_by=ConsentBy.PROXY)
        except InviteError as exc:
            status, code = _INVITE_STATUS.get(exc.reason, (409, exc.reason))
            raise HTTPException(status_code=status, detail=code) from exc
        return ok({"elder_id": elder.elder_id, "name": elder.name, "token": token})

    return router
