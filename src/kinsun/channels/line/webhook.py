"""LINE webhook：驗簽 → 正規化為 InboundMessage → 分派。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from linebot.v3.exceptions import InvalidSignatureError

from kinsun.channels.inbound import (
    BIND_FIRST_PROMPT,
    FALLBACK_PROMPT,
    NON_AUDIO_PROMPT,
    dispatch,
)
from kinsun.channels.line.channel import LineChannel
from kinsun.channels.line.messenger import LineMessenger
from kinsun.pipeline import VoicePipeline

logger = logging.getLogger("kinsun.webhook")

# 供既有測試與呼叫端沿用既有 import 路徑。
__all__ = ["BIND_FIRST_PROMPT", "FALLBACK_PROMPT", "NON_AUDIO_PROMPT", "create_app"]


def _handle_events(events, *, channel: LineChannel, pipeline, binding, gate) -> None:
    for event in events:
        try:
            msg = channel.inbound(event)
            if msg is not None:
                dispatch(msg, pipeline=pipeline, binding=binding, gate=gate)
        except Exception:  # noqa: BLE001
            # 單一事件失敗不可讓 webhook 回 500：LINE 會重送整包事件，
            # 導致重複跑管線、重複發家屬危急通知。記錄後繼續下一個事件。
            logger.exception("處理 LINE 事件失敗")


def create_app(
    *,
    parser,
    pipeline: VoicePipeline,
    messenger: LineMessenger,
    binding,
    gate,
    on_shutdown: Callable[[], None] | None = None,
) -> FastAPI:
    channel = LineChannel(messenger)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if on_shutdown is not None:
            on_shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.post("/line/webhook")
    async def line_webhook(request: Request) -> dict[str, bool]:
        body = await request.body()
        signature = request.headers.get("X-Line-Signature", "")
        try:
            events = parser.parse(body.decode("utf-8"), signature)
        except InvalidSignatureError as exc:
            raise HTTPException(status_code=400, detail="invalid signature") from exc
        # 事件處理是阻塞的重工作（ASR/LLM/HTTP），丟到 threadpool 以免卡住事件迴圈。
        await run_in_threadpool(
            _handle_events, events, channel=channel, pipeline=pipeline, binding=binding, gate=gate
        )
        return {"ok": True}

    return app
