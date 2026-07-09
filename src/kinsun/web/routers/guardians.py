"""家屬帳號資源：註冊（email＋密碼；自動建 App 通道綁定，✅ D-12）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.ratelimit import SlidingWindowRateLimiter, throttle_or_429


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)


def create_guardians_router(
    *, accounts: AccountService, rate_limiter: SlidingWindowRateLimiter
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/guardians", status_code=201)
    def register_guardian(body: RegisterIn, request: Request) -> dict:
        throttle_or_429(rate_limiter, "register", request)
        try:
            guardian, token = accounts.register_guardian_account(
                body.email, body.password, body.name
            )
        except AppAccountError as exc:
            raise HTTPException(status_code=409, detail=exc.reason) from exc
        return {"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token}

    return router
