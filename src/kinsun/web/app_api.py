"""App 認證 REST API：家屬註冊／登入、長輩裝置綁定（皆脫離 LINE）。

route handler 只轉譯 HTTP ↔ 服務層；帳號規則（雜湊、token、綁定）都在
`AccountService`。`current_app_guardian` 為家屬端 REST 換 App token 認證的
依賴（階段 3 接上）。
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from kinsun.accounts.models import ConsentBy, PrincipalType
from kinsun.accounts.service import AccountService, AppAccountError, InviteError
from kinsun.web.ratelimit import SlidingWindowRateLimiter, client_ip

# InviteError reason → HTTP 狀態碼：查無是 404，其餘皆屬「碼已不可用」的衝突。
_INVITE_STATUS = {"not_found": 404, "used": 409, "expired": 409, "too_many_attempts": 409}


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class DeviceBindingIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)


def create_app_api_router(
    *,
    accounts: AccountService,
    rate_limiter: SlidingWindowRateLimiter | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/app")
    limiter = rate_limiter or SlidingWindowRateLimiter(10, 300.0)

    def _throttle(scope: str, request: Request) -> None:
        """認證端點 per-IP 節流（✅ D-58）；三端點各自計數。"""
        if not limiter.hit(f"{scope}:{client_ip(request)}"):
            raise HTTPException(status_code=429, detail="too_many_requests")

    def current_app_guardian(authorization: str = Header(default="")) -> str:
        """驗 App token 並回 guardian_id；供家屬端 REST 依賴（階段 3 接上）。"""
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.GUARDIAN:
            raise HTTPException(status_code=401, detail="invalid_token")
        return auth.principal_id

    router.current_app_guardian = current_app_guardian  # type: ignore[attr-defined]

    @router.post("/guardians", status_code=201)
    def register_guardian(body: RegisterIn, request: Request) -> dict:
        _throttle("register", request)
        try:
            guardian, token = accounts.register_guardian_account(
                body.email, body.password, body.name
            )
        except AppAccountError as exc:
            raise HTTPException(status_code=409, detail=exc.reason) from exc
        return {"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token}

    @router.post("/sessions")
    def login(body: LoginIn, request: Request) -> dict:
        _throttle("login", request)
        try:
            guardian, token = accounts.login_guardian(body.email, body.password)
        except AppAccountError as exc:
            raise HTTPException(status_code=401, detail=exc.reason) from exc
        return {"guardian_id": guardian.guardian_id, "name": guardian.name, "token": token}

    @router.post("/device-bindings", status_code=201)
    def create_device_binding(body: DeviceBindingIn, request: Request) -> dict:
        _throttle("bind", request)
        try:
            # App 端綁定碼由家屬產生、多半由家屬替長輩操作 → 同意主體記 PROXY。
            elder, token = accounts.bind_elder_device(body.code, consent_by=ConsentBy.PROXY)
        except InviteError as exc:
            raise HTTPException(
                status_code=_INVITE_STATUS.get(exc.reason, 409), detail=exc.reason
            ) from exc
        return {"elder_id": elder.elder_id, "name": elder.name, "token": token}

    return router
