"""後台守則資源：檢視生效中的守則、撤銷學歪的守則。

角色是**事後撤銷（opt-out）**，不是事前批准——守則由每晚反思自動生效、無人審佇列，
故本路由刻意不提供「採用」動作（沒有待審佇列可批准）。它存在的理由只有一個：逃生口。
守則學歪了要能立刻撤掉，而不必等下次部署。

回傳帶 `evidence` 與 `observed_days`：要判斷一條守則該不該撤，得看得到金孫是憑什麼
學到它的。注意 `evidence` 只在本後台 API 出現，**絕不進 system prompt**（注入端只取
`content`，Task 7 以測試釘死）。

與 admin.py（唯讀觀測）分檔的理由同 admin_jobs.py：本檔的 PATCH 會改變系統狀態。
金鑰驗證共用 admin.py 的 `build_require_admin`。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from kinsun.strategies.models import (
    STRATEGY_STATUS_ADOPTED,
    STRATEGY_STATUS_REVOKED,
    STRATEGY_STATUSES,
    Strategy,
)
from kinsun.strategies.store import StrategyStore
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.admin import build_require_admin

# 目前唯一支援的動作。刻意不收 "adopt"：守則自動生效，後台只負責撤銷。
ACTION_REVOKE = "revoke"


class StrategyActionBody(BaseModel):
    action: str  # 僅接受 "revoke"；型別留 str（而非 Literal）以便回 400 而非 422


def create_admin_strategies_router(
    *,
    admin_api_key: str,
    strategies: StrategyStore,
) -> APIRouter:
    router = APIRouter(tags=["admin"])
    require_admin = build_require_admin(admin_api_key)

    @router.get("/strategies", dependencies=[Depends(require_admin)])
    def list_strategies(status: str = Query(default=STRATEGY_STATUS_ADOPTED)) -> dict:
        """跨長輩列出某狀態的守則（預設 adopted＝目前正在影響金孫的那些）。"""
        if status not in STRATEGY_STATUSES:
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_STATUS)
        return ok([_strategy_json(s) for s in strategies.list_for_status(status)])

    @router.patch("/strategies/{strategy_id}", dependencies=[Depends(require_admin)])
    def update_strategy(strategy_id: str, body: StrategyActionBody) -> dict:
        if body.action != ACTION_REVOKE:
            raise HTTPException(status_code=400, detail=ErrorCode.INVALID_ACTION)
        # 命中與否交給 revoke() 回報：它是一句條件式 UPDATE（WHERE status='adopted'
        # RETURNING），撤到才回 True。不能改成「先查 adopted 清單、再撤」——兩步之間
        # 夜間反思剛好 commit 一個 supersede，就會撲空卻回報「已撤銷」，而那條守則的
        # 改寫版正生效中：這個逃生口對操作者說謊，比壞掉更糟。
        # 兩人同時撤同一條時只有一人拿到 200，另一人 404（守則確實已不在生效中）。
        if not strategies.revoke(strategy_id):
            raise HTTPException(status_code=404, detail=ErrorCode.STRATEGY_NOT_FOUND)
        return ok({"strategy_id": strategy_id, "status": STRATEGY_STATUS_REVOKED})

    return router


def _strategy_json(s: Strategy) -> dict:
    return {
        "strategy_id": s.strategy_id,
        "elder_id": s.elder_id,
        "content": s.content,
        "category": s.category,
        "evidence": s.evidence,
        "observed_days": s.observed_days,
        "status": s.status,
        "supersedes_strategy_id": s.supersedes_strategy_id,
        "created_at": s.created_at,
        "revoked_at": s.revoked_at,
    }
