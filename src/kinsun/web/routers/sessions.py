"""登入會話資源：家屬登入（登出撤銷端點於乙-3 增補，D-25）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.ratelimit import SlidingWindowRateLimiter, throttle_or_429


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def create_sessions_router(
    *, accounts: AccountService, rate_limiter: SlidingWindowRateLimiter
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/sessions")
    def login(body: LoginIn, request: Request) -> dict:
        throttle_or_429(rate_limiter, "login", request)
        try:
            guardian, token = accounts.login_guardian(body.email, body.password)
        except AppAccountError as exc:
            raise HTTPException(status_code=401, detail=exc.reason) from exc
        return {"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token}

    return router
