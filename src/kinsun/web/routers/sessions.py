"""登入會話資源：家屬登入＋登出撤銷（✅ D-25 修訂：token 永久記住、可主動登出）。"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.models import PrincipalType
from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.envelope import ok
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
        return ok({"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token})

    @router.delete("/sessions", status_code=204)
    def logout(authorization: str = Header(default="")) -> None:
        """登出＝撤銷當前 token（被盜或換機時的主動撤銷手段）。"""
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.GUARDIAN:
            raise HTTPException(status_code=401, detail="invalid_token")
        accounts.logout(token)

    return router
