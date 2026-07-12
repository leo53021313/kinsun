"""路由共用依賴：家屬雙認證、可及範圍守門、App token 認證。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Header, HTTPException

from kinsun.accounts.models import Elder, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.web.auth import AuthError, LiffVerifier
from kinsun.web.errors import ErrorCode


@dataclass(frozen=True)
class GuardianAuth:
    """家屬請求身分：App token 直接得 guardian_id；LIFF 首次使用可能尚無家屬紀錄。"""

    guardian_id: str | None
    line_user_id: str | None


def build_current_guardian(
    verifier: LiffVerifier, accounts: AccountService
) -> Callable[..., GuardianAuth]:
    """家屬面雙認證依賴：先查 App token（本地查表、快），miss 再走 LIFF 驗證（打 LINE API）。"""

    def current_guardian(authorization: str = Header(default="")) -> GuardianAuth:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail=ErrorCode.MISSING_TOKEN)
        api_token = accounts.authenticate_token(token)
        if api_token is not None:
            if api_token.principal_type is not PrincipalType.GUARDIAN:
                raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
            return GuardianAuth(api_token.principal_id, None)
        try:
            return GuardianAuth(None, verifier.verify(token))
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN) from exc

    return current_guardian


def build_current_app_guardian(accounts: AccountService) -> Callable[..., str]:
    """App token（家屬）認證依賴：回 guardian_id；非家屬 token 一律 401。"""

    def current_app_guardian(authorization: str = Header(default="")) -> str:
        token = authorization.removeprefix("Bearer ").strip()
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.GUARDIAN:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        return auth.principal_id

    return current_app_guardian


class GuardianScope:
    """家屬可及範圍守門：長輩操作前先確認在管理名單內（否則 404 不洩漏存在性）。"""

    def __init__(self, accounts: AccountService) -> None:
        self._accounts = accounts

    def elders_of(self, auth: GuardianAuth) -> list[Elder]:
        if auth.guardian_id is not None:
            return self._accounts.elders_of_guardian(auth.guardian_id)
        return self._accounts.elders_managed_by(auth.line_user_id or "")

    def assert_manages(self, auth: GuardianAuth, elder_id: str) -> None:
        if elder_id not in {e.elder_id for e in self.elders_of(auth)}:
            raise HTTPException(status_code=404, detail=ErrorCode.ELDER_NOT_FOUND)
