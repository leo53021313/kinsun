"""組裝根：把設定與各元件接成可服務的 FastAPI app。

啟動：uv run uvicorn "kinsun.app:build_app" --factory --reload
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from linebot.v3 import WebhookParser

from kinsun.agent import CareAgent
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.channels.line.webhook import create_app
from kinsun.config import load_settings
from kinsun.llm import GeminiClient
from kinsun.memory.store import SqliteMemoryStore
from kinsun.pipeline import VoicePipeline
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import TextBubbleTts


def build_app() -> FastAPI:
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    memory = SqliteMemoryStore(
        settings.memory_db_path,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    pipeline = VoicePipeline(
        asr=build_asr_client(settings),
        agent=CareAgent(
            GeminiClient(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout=settings.llm_timeout_seconds,
            ),
            memory,
        ),
        tts=TextBubbleTts(),
    )
    messenger = LineApiMessenger(settings.line_channel_access_token)
    parser = WebhookParser(settings.line_channel_secret)
    return create_app(parser=parser, pipeline=pipeline, messenger=messenger)
