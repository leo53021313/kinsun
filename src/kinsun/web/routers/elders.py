"""長輩資源：列表（登入家屬管理的）、建檔＋首綁邀請碼、產家屬邀請碼。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService
from kinsun.web.envelope import ok
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class CreateElderIn(BaseModel):
    name: str
    guardian_name: str = ""


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
            raise HTTPException(status_code=400, detail="name required")
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

    return router
