"""LINE webhook：驗簽 → 解析事件 → 跑語音管線 → 回覆。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from linebot.v3.exceptions import InvalidSignatureError

from kinsun.channels.line.messenger import LineMessenger
from kinsun.llm import LLMError
from kinsun.memory.store import MemoryError
from kinsun.pipeline import VoicePipeline
from kinsun.speech.asr import ASRError

NON_AUDIO_PROMPT = "金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話。"
FALLBACK_PROMPT = "金孫剛剛沒聽清楚，您可以再說一次嗎？"
BIND_FIRST_PROMPT = (
    "金孫需要先完成綁定才能陪您聊天喔。請把家人給您的邀請碼貼到這裡，或回覆「設定」開始。"
)


def _handle_events(
    events, pipeline: VoicePipeline, messenger: LineMessenger, binding, gate
) -> None:
    for event in events:
        message = getattr(event, "message", None)
        reply_token = getattr(event, "reply_token", None)
        if message is None or reply_token is None:
            continue
        source = getattr(event, "source", None)
        session_id = getattr(source, "user_id", None) or "unknown"
        mtype = getattr(message, "type", None)
        if mtype == "text":
            reply = binding.handle(session_id, getattr(message, "text", "") or "")
            messenger.reply_text(reply_token, reply if reply is not None else NON_AUDIO_PROMPT)
            continue
        if mtype != "audio":
            messenger.reply_text(reply_token, NON_AUDIO_PROMPT)
            continue
        if not gate.allows(session_id):
            messenger.reply_text(reply_token, BIND_FIRST_PROMPT)
            continue
        try:
            audio = messenger.get_audio(message.id)
            result = pipeline.process(audio, session_id=session_id)
            messenger.reply_text(reply_token, result.text)
        except (ASRError, LLMError, MemoryError):
            messenger.reply_text(reply_token, FALLBACK_PROMPT)


def create_app(
    *, parser, pipeline: VoicePipeline, messenger: LineMessenger, binding, gate
) -> FastAPI:
    app = FastAPI()

    @app.post("/line/webhook")
    async def line_webhook(request: Request) -> dict[str, bool]:
        body = await request.body()
        signature = request.headers.get("X-Line-Signature", "")
        try:
            events = parser.parse(body.decode("utf-8"), signature)
        except InvalidSignatureError as exc:
            raise HTTPException(status_code=400, detail="invalid signature") from exc
        _handle_events(events, pipeline, messenger, binding, gate)
        return {"ok": True}

    return app
