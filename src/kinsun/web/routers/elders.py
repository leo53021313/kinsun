"""長輩資源：列表（登入家屬管理的）、建檔＋首綁邀請碼、產家屬邀請碼。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kinsun import personas
from kinsun.accounts.models import InviteRole
from kinsun.accounts.service import AccountService, AppAccountError
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.deps import GuardianAuth, GuardianScope


class CreateElderIn(BaseModel):
    """payload 三端統一為 {name}（✅ 庚-29／F-9）：LIFF 首次建家屬檔的命名
    改取 ID token 的 LINE 顯示名稱（GuardianAuth.display_name），不再由前端自送。

    nickname＝金孫對長輩的稱謂（如「秀英阿嬤」，2026-07-17）；選填，空＝未設定。"""

    name: str
    nickname: str = Field(default="", max_length=50)


class ElderProfileIn(BaseModel):
    """家屬補設／更改稱謂；空字串＝清除（情境注入退回名字保底）。"""

    nickname: str = Field(max_length=50)


class ElderPersonaIn(BaseModel):
    """家屬更改金孫的人設（2026-08-05）。值域由 handler 對照 `personas.py` 驗。

    ⚠️ 刻意不併進 `ElderProfileIn`：那支是整份 upsert，前端漏帶 `nickname` 就會
    把稱謂洗掉，而稱謂設錯的後果是金孫每輪亂猜「阿公／阿嬤」（2026-07-17 實測
    過的真實問題）。獨立端點讓這種誤用不可能發生。
    """

    persona: str = Field(max_length=50)


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
        return ok(
            [
                {
                    "elder_id": e.elder_id,
                    "name": e.name,
                    "nickname": e.nickname,
                    "persona": e.persona,
                }
                for e in elders
            ]
        )

    @router.post("/elders", status_code=201)
    def create_elder(body: CreateElderIn, auth: GuardianAuth = Depends(current_guardian)) -> dict:
        name = body.name.strip()
        nickname = body.nickname.strip()
        if not name:
            raise HTTPException(status_code=400, detail=ErrorCode.NAME_REQUIRED)
        if auth.guardian_id is not None:
            elder = accounts.create_elder_for_guardian(auth.guardian_id, name, nickname)
        else:
            elder = accounts.create_elder(
                auth.line_user_id or "", auth.display_name, name, nickname
            )
        invite = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
        return ok(
            {
                "elder_id": elder.elder_id,
                "name": elder.name,
                "nickname": elder.nickname,
                # ⚠️ 新建的長輩也要回人設（2026-08-05）：前端把這個物件直接放進
                # 清單，少一格會讓剛建立的那筆在畫面上與其他筆不同形狀，要重新
                # 整理才對——A-10 就是同一個坑（後端有回、前端丟掉）。
                "persona": elder.persona,
                "invite_code": invite.code,
            }
        )

    @router.put("/elders/{elder_id}/profile")
    def update_elder_profile(
        elder_id: str, body: ElderProfileIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        """家屬補設／更改稱謂（2026-07-17）：PUT＝upsert，重呼即改。"""
        scope.assert_manages(auth, elder_id)
        elder = accounts.set_elder_nickname(elder_id, body.nickname.strip())
        return ok({"elder_id": elder.elder_id, "nickname": elder.nickname})

    @router.put("/elders/{elder_id}/persona")
    def update_elder_persona(
        elder_id: str, body: ElderPersonaIn, auth: GuardianAuth = Depends(current_guardian)
    ) -> dict:
        """家屬更改金孫的人設（2026-08-05）。下一輪對話即生效。"""
        scope.assert_manages(auth, elder_id)
        persona_id = body.persona.strip()
        if persona_id not in personas.persona_ids():
            # 邊界要驗證：認不得的值當場擋下，不讓它進資料庫。
            # ⚠️ 與 `personas.get_persona` 讀取時退回預設的寬容行為是刻意的分工：
            # 寫入嚴格、讀取寬容——資料庫裡萬一有髒值也不會讓長輩的對話卡死。
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_PERSONA)
        elder = accounts.set_elder_persona(elder_id, persona_id)
        return ok({"elder_id": elder.elder_id, "persona": elder.persona})

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
