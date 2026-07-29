"""路由共用依賴：家屬雙認證、可及範圍守門、App token 認證。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Header, HTTPException

from kinsun.accounts.models import Elder, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.web.auth import AuthError, LiffVerifier
from kinsun.web.errors import ErrorCode


def strip_bearer(authorization: str) -> str:
    """從 Authorization 標頭取出 token（A-15，2026-07-29）。

    RFC 7235 明訂 auth-scheme **大小寫不敏感**，故 `bearer`／`BEARER` 都要認得。
    原本各處寫 `removeprefix("Bearer ")`，小寫進來時剝不掉，token 變成
    `"bearer xxx"` → 401 `invalid_token`——而那個症狀長得**跟 token 失效一模一樣**，
    呼叫端會去查 token 生命週期、查有沒有被撤銷，查不到真正的原因只是 B 沒大寫。

    本檔的 `current_guardian` 早就用 `scheme.lower()` 做對了，其餘幾支沒有：
    這是漂移不是設計，故抽成單一出處。

    沒帶 scheme 的裸 token 維持既有寬容（原 `removeprefix` 對不符前綴的字串是原樣
    回傳）；只剝一次，token 內容剛好長得像 scheme 時不會被連帶吃掉。
    """
    scheme, separator, rest = authorization.partition(" ")
    if separator and scheme.lower() == "bearer":
        return rest.strip()
    return authorization.strip()


@dataclass(frozen=True)
class GuardianAuth:
    """家屬請求身分：App token 直接得 guardian_id；LIFF 首次使用可能尚無家屬紀錄。"""

    guardian_id: str | None
    line_user_id: str | None
    # LIFF 路徑的 LINE 顯示名稱（✅ 庚-29）：首次建家屬檔命名用；App 路徑為空。
    display_name: str = ""


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
            identity = verifier.verify(token)
            return GuardianAuth(None, identity.line_user_id, identity.display_name)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN) from exc

    return current_guardian


def build_current_app_guardian(accounts: AccountService) -> Callable[..., str]:
    """App token（家屬）認證依賴：回 guardian_id；非家屬 token 一律 401。"""

    def current_app_guardian(authorization: str = Header(default="")) -> str:
        token = strip_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail=ErrorCode.MISSING_TOKEN)
        auth = accounts.authenticate_token(token)
        if auth is None or auth.principal_type is not PrincipalType.GUARDIAN:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        return auth.principal_id

    return current_app_guardian


def build_current_app_elder(accounts: AccountService) -> Callable[..., str]:
    """App token（長輩）認證依賴：回 elder_id；非長輩 token 一律 401。

    與 `build_current_app_guardian` 對稱。`channels/app/turns.py` 另有一份同語意的
    區域 `current_elder`（該處還要複核同意閘門），兩者刻意不合併：對講機每一輪都
    新產生資料流，必須複核同意；本依賴只服務唯讀端點，且長輩解綁時 token 一併撤銷
    （`accounts/service.py:405-410`），認證這一關就已擋下。
    """

    def current_app_elder(authorization: str = Header(default="")) -> str:
        token = strip_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail=ErrorCode.MISSING_TOKEN)
        auth = accounts.authenticate_token(token)
        if auth is None or auth.principal_type is not PrincipalType.ELDER:
            raise HTTPException(status_code=401, detail=ErrorCode.INVALID_TOKEN)
        return auth.principal_id

    return current_app_elder


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
