"""組裝根：把設定與各元件接成可服務的 FastAPI app。

啟動：uv run uvicorn "kinsun.app:build_app" --factory --reload
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from linebot.v3 import WebhookParser

from kinsun.accounts.repository import PgAccountRepository
from kinsun.accounts.service import AccountService
from kinsun.agent import CareAgent
from kinsun.binding.flow import BindingFlow
from kinsun.binding.gate import ConsentGate
from kinsun.binding.session import PgBindingSessionStore
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.channels.line.webhook import create_app
from kinsun.config import load_settings
from kinsun.db import ensure_schema
from kinsun.llm import GeminiClient
from kinsun.longterm.store import Mem0LongTermStore
from kinsun.mem0_factory import build_mem0_memory
from kinsun.memory.store import PgMemoryStore
from kinsun.pipeline import VoicePipeline
from kinsun.recall import MemoryContext
from kinsun.safety.classifier import LlmRiskClassifier
from kinsun.safety.detector import RiskDetector
from kinsun.safety.notifier import LineGuardianNotifier
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import TextBubbleTts
from kinsun.tools.registry import ToolRegistry
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler


def build_app() -> FastAPI:
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    ensure_schema(settings.database_url)
    memory = PgMemoryStore(
        settings.database_url,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    gemini = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.llm_timeout_seconds,
    )
    long_term = Mem0LongTermStore(build_mem0_memory(settings), top_k=settings.longterm_top_k)
    context = MemoryContext(long_term)
    accounts = AccountService(
        PgAccountRepository(settings.database_url),
        clock=lambda: datetime.now(tz),
        ttl_hours=settings.invite_ttl_hours,
        max_attempts=settings.invite_max_attempts,
    )
    messenger = LineApiMessenger(settings.line_channel_access_token)
    registry = ToolRegistry()
    registry.register(WEATHER_SPEC, build_weather_handler())
    pipeline = VoicePipeline(
        asr=build_asr_client(settings),
        agent=CareAgent(gemini, memory, context, tools=registry),
        tts=TextBubbleTts(),
        detector=RiskDetector(LlmRiskClassifier(gemini)),
        notifier=LineGuardianNotifier(accounts, messenger),
    )
    binding = BindingFlow(
        accounts,
        PgBindingSessionStore(settings.database_url),
        messenger,
        clock=lambda: datetime.now(tz),
        session_ttl_seconds=settings.binding_session_ttl_minutes * 60,
    )
    gate = ConsentGate(accounts)
    parser = WebhookParser(settings.line_channel_secret)
    return create_app(
        parser=parser, pipeline=pipeline, messenger=messenger, binding=binding, gate=gate
    )
