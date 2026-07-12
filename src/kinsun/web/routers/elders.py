"""長輩資源：列表（登入家屬管理的）、建檔＋首綁邀請碼、產家屬邀請碼。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class CreateElderIn(BaseModel):
    name: str
    guardian_name: str = ""


class ElderAccountIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)


def create_elders_router(
    *,
    accounts: AccountService,
    current_guardian: Callable[..., GuardianAuth],
    scope: GuardianScope,
) -> APIRouter:
    router = APIRouter(tags=["elders"])

    @router.get("/elders")
    def my_elders(auth: GuardianAuth = Depends(current_guardian)) -> dict:
        """列登入家屬管理的長輩（✅ D-28：/me/elders 改名；列表＝data 裸陣列）。"""
        elders = scope.elders_of(auth)
        return ok([{"elder_id": e.elder_id, "name": e.name} for e in elders])

    @router.post("/elders", status_code=201)
    def create_elder(body: CreateElderIn, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name_required")
        if auth.guardian_id is not None:
            elder = accounts.create_elder_for_guardian(auth.guardian_id, name)
        else:
            elder = accounts.create_elder(auth.line_user_id or "", body.guardian_name, name)
        invite = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
        return ok({"elder_id": elder.elder_id, "name": elder.name, "invite_code": invite.code})

    @router.post("/elders/{elder_id}/guardian-invites", status_code=201)
    def create_guardian_invite(
        elder_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        scope.assert_manages(auth, elder_id)
        invite = accounts.generate_invite(elder_id, InviteRole.GUARDIAN)
        return ok({"invite_code": invite.code})

    @router.delete("/elders/{elder_id}/device-bindings")
    def revoke_device_bindings(
        elder_id: str, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        """作廢長輩裝置重綁（✅ D-25 修訂）：撤銷舊裝置 token＋重發綁定碼。

        回 200＋新綁定碼（非 204——重綁流程需要新碼，省一次額外請求）。
        """
        scope.assert_manages(auth, elder_id)
        invite = accounts.revoke_elder_device(elder_id)
        return ok({"invite_code": invite.code})

    @router.put("/elders/{elder_id}/account")
    def set_elder_account(
        elder_id: str, body: ElderAccountIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        """家屬代辦長輩帳密（✅ D-71 己-6）：PUT＝upsert，重呼即重設密碼／換號碼。"""
        scope.assert_manages(auth, elder_id)
        try:
            accounts.register_elder_account(elder_id, body.phone, body.password)
        except AppAccountError as exc:
            status = 409 if exc.reason == "phone_taken" else 400
            raise HTTPException(status_code=status, detail=exc.reason) from exc
        return ok({"elder_id": elder_id})

    return router
