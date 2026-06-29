"""LINE webhook：驗簽 → 解析事件 → 跑語音管線 → 回覆。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from linebot.v3.exceptions import InvalidSignatureError

from kinsun.channels.line.messenger import LineMessenger
from kinsun.llm import LLMError
from kinsun.memory.store import MemoryError
from kinsun.pipeline import VoicePipeline
from kinsun.speech.asr import ASRError

logger = logging.getLogger("kinsun.webhook")

NON_AUDIO_PROMPT = "金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
FALLBACK_PROMPT = "金孫剛剛沒聽清楚，您可以再說一次嗎？"
BIND_FIRST_PROMPT = (
    "金孫需要先完成綁定才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


def _process_event(event, pipeline: VoicePipeline, messenger: LineMessenger, binding, gate) -> None:
    message = getattr(event, "message", None)
    reply_token = getattr(event, "reply_token", None)
    if message is None or reply_token is None:
        return
    source = getattr(event, "source", None)
    session_id = getattr(source, "user_id", None) or "unknown"
    mtype = getattr(message, "type", None)
    if mtype == "text":
        reply = binding.handle(session_id, getattr(message, "text", "") or "")
        messenger.reply_text(reply_token, reply if reply is not None else NON_AUDIO_PROMPT)
        return
    if mtype != "audio":
        messenger.reply_text(reply_token, NON_AUDIO_PROMPT)
        return
    if not gate.allows(session_id):
        messenger.reply_text(reply_token, BIND_FIRST_PROMPT)
        return
    try:
        audio = messenger.get_audio(message.id)
        result = pipeline.process(audio, session_id=session_id)
        messenger.reply_text(reply_token, result.text)
    except (ASRError, LLMError, MemoryError):
        messenger.reply_text(reply_token, FALLBACK_PROMPT)


def _handle_events(
    events, pipeline: VoicePipeline, messenger: LineMessenger, binding, gate
) -> None:
    for event in events:
        try:
            _process_event(event, pipeline, messenger, binding, gate)
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
        await run_in_threadpool(_handle_events, events, pipeline, messenger, binding, gate)
        return {"ok": True}

    return app
