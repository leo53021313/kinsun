"""公開 meta 端點（spec 2026-07-12 §3.1）：向前端下發伺服器模式，不含機敏值。

App 與觀測後台啟動時查一次；只回布林旗標，故不需認證。
取不到時前端一律當 false（fail-safe，正式行為不受影響）。
"""

from __future__ import annotations

from fastapi import APIRouter

from kinsun.web.envelope import ok


def create_meta_router(*, internal_testing_enabled: bool) -> APIRouter:
    router = APIRouter(tags=["meta"])

    @router.get("/meta")
    def meta() -> dict:
        return ok({"internal_testing": internal_testing_enabled})

    return router
