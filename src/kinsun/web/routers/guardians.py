"""家屬帳號資源：註冊（email＋密碼；自動建 App 通道綁定，✅ D-12）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.envelope import ok
from kinsun.web.ratelimit import RateLimiter, throttle_or_429


class RegisterIn(BaseModel):
    # email 基本格式（✅ D-61 丙-11）：不引入 email-validator 依賴，擋明顯錯誤即可。
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)


def create_guardians_router(*, accounts: AccountService, rate_limiter: RateLimiter) -> APIRouter:
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
        return ok({"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token})

    return router
