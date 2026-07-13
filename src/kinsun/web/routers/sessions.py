"""登入會話資源：家屬登入＋長輩登入＋登出撤銷（token 永久記住、可主動登出）。

長輩帳密（✅ D-71 己-6）：帳號＝手機號碼、由家屬代辦；只管「重登」——
首次一定要掃碼配對，未配對回 403 not_paired 提示先掃碼。"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.models import PrincipalType
from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.ratelimit import RateLimiter, throttle_or_429


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ElderLoginIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    password: str = Field(min_length=1, max_length=128)


def create_sessions_router(*, accounts: AccountService, rate_limiter: RateLimiter) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/sessions")
    def login(body: LoginIn, request: Request) -> dict:
        throttle_or_429(rate_limiter, "login", request)
        try:
            guardian, token = accounts.login_guardian(body.email, body.password)
        except AppAccountError as exc:
            raise HTTPException(status_code=401, detail=exc.reason) from exc
        return ok({"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token})

    @router.post("/elder-sessions")
    def elder_login(body: ElderLoginIn, request: Request) -> dict:
        throttle_or_429(rate_limiter, "elder-login", request)
        try:
            elder, token = accounts.login_elder(body.phone, body.password)
        except AppAccountError as exc:
            status = 403 if exc.reason == "not_paired" else 401
            raise HTTPException(status_code=status, detail=exc.reason) from exc
        return ok({"elder_id": elder.elder_id, "name": elder.name, "token": token})

    @router.delete("/sessions", status_code=204)
    def logout(authorization: str = Header(default="")) -> None:
        """登出＝撤銷當前 token（被盜或換機時的主動撤銷手段）。
        家屬與長輩 token 皆可（✅ 庚-42：長輩自助登出）；「登出所有裝置」仍限家屬。"""
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        accounts.logout(token)

    @router.delete("/sessions/all", status_code=204)
    def logout_all(authorization: str = Header(default="")) -> None:
        """登出所有裝置＝撤銷該家屬全部 token（庚-05／A-47：永久 token 外洩補救）。"""
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.GUARDIAN:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        accounts.logout_all_devices(auth.principal_id)

    return router
