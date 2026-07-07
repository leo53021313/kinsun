"""組裝根：把設定與各元件接成可服務的 FastAPI app。

啟動：uv run uvicorn "kinsun.app:build_app" --factory --reload
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from linebot.v3 import WebhookParser

from kinsun.appointments.flow import AppointmentMenu
from kinsun.audio.publisher import build_audio_publisher
from kinsun.binding.flow import BindingFlow
from kinsun.binding.gate import AllowAllGate, ConsentGate
from kinsun.binding.session import PgBindingSessionStore
from kinsun.channels.inbound import VoiceReplyDelivery
from kinsun.channels.line.webhook import create_app
from kinsun.composition import assemble_core, build_externals
from kinsun.config import load_dotenv, load_settings
from kinsun.medications.flow import MedicationMenu
from kinsun.pipeline import VoicePipeline
from kinsun.safety.classifier import LlmRiskClassifier
from kinsun.safety.detector import RiskDetector
from kinsun.safety.events import PgRiskEventStore
from kinsun.safety.notifier import GuardianNotifier
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import build_tts_client
from kinsun.web.admin_api import create_admin_api_router
from kinsun.web.api import create_api_router
from kinsun.web.app_api import create_app_api_router
from kinsun.web.auth import LineIdTokenVerifier


def build_app() -> FastAPI:
    load_dotenv()
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)

    def clock() -> datetime:
        return datetime.now(tz)

    externals = build_externals(settings)
    core = assemble_core(settings, externals, clock=clock)
    db = core.db

    # --- web 專屬接線 ---
    risk_events = PgRiskEventStore(db, clock=clock, new_id=lambda: uuid.uuid4().hex)
    # 進站音檔託管：有 Supabase 憑證就啟用（獨立於 TTS 後端選擇）。
    inbound_audio = (
        build_audio_publisher(
            settings,
            clock=clock,
            new_id=lambda: uuid.uuid4().hex,
            prefix="inbound",
        )
        if settings.supabase_url and settings.supabase_service_key
        else None
    )
    pipeline = VoicePipeline(
        asr=build_asr_client(settings),
        agent=core.agent,
        tts=build_tts_client(settings),
        detector=RiskDetector(LlmRiskClassifier(core.gemini)),
        notifier=GuardianNotifier(core.accounts, core.router),
        risk_events=risk_events,
        traces=core.traces,
        model_name=settings.gemini_model,
    )
    binding_sessions = PgBindingSessionStore(db)
    medication_menu = MedicationMenu(core.medications, core.accounts, binding_sessions, clock=clock)
    appointment_menu = AppointmentMenu(
        core.appointments, core.accounts, binding_sessions, clock=clock
    )

    def _link_menu(line_user_id: str) -> None:
        core.messenger.link_rich_menu(line_user_id, settings.rich_menu_id)

    on_guardian_bound = _link_menu if settings.rich_menu_id else None
    binding = BindingFlow(
        core.accounts,
        binding_sessions,
        core.messenger,
        medication_menu,
        appointment_menu,
        clock=clock,
        session_ttl_seconds=settings.binding_session_ttl_minutes * 60,
        on_guardian_bound=on_guardian_bound,
    )
    gate = ConsentGate(core.accounts) if settings.binding_gate_enabled else AllowAllGate()
    publisher = (
        build_audio_publisher(settings, clock=clock, new_id=lambda: uuid.uuid4().hex)
        if settings.tts_backend == "dgx"
        else None
    )
    voice = VoiceReplyDelivery(
        publisher, settings.tts_reply_text, show_transcript=settings.asr_debug_show_transcript
    )
    parser = WebhookParser(settings.line_channel_secret)
    app = create_app(
        parser=parser,
        pipeline=pipeline,
        messenger=core.messenger,
        binding=binding,
        gate=gate,
        voice=voice,
        traces=core.traces,
        inbound_audio=inbound_audio,
        text_input_enabled=settings.line_text_input_enabled,
        on_shutdown=db.close,
    )
    verifier = LineIdTokenVerifier(settings.liff_channel_id, settings.liff_timeout_seconds)
    app.include_router(
        create_api_router(
            verifier=verifier,
            accounts=core.accounts,
            medications=core.medications,
            appointments=core.appointments,
            clock=clock,
            risk_events=risk_events,
            reminder_logs=core.reminder_logs,
        )
    )
    app.include_router(
        create_admin_api_router(
            admin_api_key=settings.admin_api_key,
            traces=core.traces,
            clock=clock,
        )
    )
    app.include_router(create_app_api_router(accounts=core.accounts))
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/liff", StaticFiles(directory=dist, html=True), name="liff")
    admin_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist-admin"
    if admin_dist.is_dir():
        app.mount("/admin", StaticFiles(directory=admin_dist, html=True), name="admin")
    return app
