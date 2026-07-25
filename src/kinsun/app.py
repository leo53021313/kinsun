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

from kinsun import tracing
from kinsun.audio.publisher import build_audio_publisher
from kinsun.binding.flow import BindingFlow
from kinsun.binding.gate import AllowAllGate, ConsentGate
from kinsun.binding.session import PgBindingSessionStore
from kinsun.channels.app.turns import create_app_turns_router
from kinsun.channels.inbound import VoiceReplyDelivery
from kinsun.channels.line.webhook import create_app
from kinsun.composition import assemble_core, build_externals
from kinsun.config import load_dotenv, load_settings
from kinsun.llm import build_gemini_for
from kinsun.pipeline import VoicePipeline
from kinsun.rag.releases import PgRagReleaseStore
from kinsun.safety.classifier import LlmRiskClassifier
from kinsun.safety.deliveries import PgRiskNotificationLogStore
from kinsun.safety.detector import RiskDetector
from kinsun.safety.moderation import AbuseModerator, LlmAbuseClassifier
from kinsun.safety.notifier import GuardianNotifier
from kinsun.scheduler.state import PgScheduleStateStore
from kinsun.scheduler.worker import build_jobs
from kinsun.schedules.flow import ScheduleMenu
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import build_tts_client
from kinsun.web.auth import LineIdTokenVerifier
from kinsun.web.envelope import install_error_envelope
from kinsun.web.ratelimit import PgRateLimiter
from kinsun.web.routers import (
    create_admin_jobs_router,
    create_admin_router,
    create_admin_strategies_router,
    create_app_auth_router,
    create_guardian_face_router,
    create_meta_router,
)
from kinsun.web.security import install_security_headers


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
    risk_events = core.risk_events
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
    # 危急分級按用途配模型（✅ D-16 丁-5）：與主模型相同時共用連線。
    safety_llm = (
        core.gemini
        if settings.gemini_model_safety == settings.gemini_model
        else build_gemini_for(
            settings, settings.gemini_model_safety, client_wrapper=tracing.wrap_genai
        )
    )
    # 危急送達留痕：notifier 寫入、admin 觀測讀取，共用同一實例。
    deliveries = PgRiskNotificationLogStore(db, clock=clock, new_id=lambda: uuid.uuid4().hex)
    # 濫用審核（2026-07-25）：預設開；設 SAFETY_MODERATION_ENABLED=false 則傳 None，
    # 管線整段不執行審核、不多花 LLM 呼叫（維運逃生口）。
    # 與危急分級共用同一顆 safety 模型——兩者都是短輸入的結構化判斷。
    moderator = (
        AbuseModerator(
            LlmAbuseClassifier(safety_llm),
            min_confidence=settings.safety_moderation_min_confidence,
        )
        if settings.safety_moderation_enabled
        else None
    )
    pipeline = VoicePipeline(
        asr=build_asr_client(settings),
        agent=core.agent,
        tts=build_tts_client(settings),
        detector=RiskDetector(
            LlmRiskClassifier(safety_llm),
            mid=settings.safety_confidence_mid,
        ),
        notifier=GuardianNotifier(
            core.accounts,
            core.router,
            deliveries=deliveries,
        ),
        risk_events=risk_events,
        traces=core.traces,
        model_name=settings.gemini_model,
        safety_model_name=settings.gemini_model_safety,
        # 長輩開口即標記時間窗內的提醒為已回應：反思的行為訊號來源（✅ Task 4）。
        reminder_logs=core.reminder_logs,
        response_window_seconds=settings.reflection_response_window_minutes * 60,
        moderator=moderator,
    )
    binding_sessions = PgBindingSessionStore(db)
    schedule_menu = ScheduleMenu(
        core.schedules,
        core.accounts,
        binding_sessions,
        clock=clock,
        # 四時段鐘點自此只是「家屬選 1～4 時的預設值」，不再是全系統派送鐘點。
        slot_hours={
            "morning": settings.medication_morning_hour,
            "noon": settings.medication_noon_hour,
            "evening": settings.medication_evening_hour,
            "bedtime": settings.medication_bedtime_hour,
        },
        appointment_hour=settings.appointment_reminder_hour,
    )

    def _link_menu(line_user_id: str) -> None:
        core.messenger.link_rich_menu(line_user_id, settings.rich_menu_id)

    on_guardian_bound = _link_menu if settings.rich_menu_id else None
    binding = BindingFlow(
        core.accounts,
        binding_sessions,
        core.messenger,
        schedule_menu,
        clock=clock,
        session_ttl_seconds=settings.binding_session_ttl_minutes * 60,
        on_guardian_bound=on_guardian_bound,
    )
    gate = (
        ConsentGate(core.accounts)
        if settings.binding_gate_enabled
        else AllowAllGate(core.accounts)  # 旁路模式也解析 elder_id（✅ D-19）
    )
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
    install_error_envelope(app)  # HTTPException → 統一信封（✅ D-23 乙-1）
    install_security_headers(app)  # 基本安全標頭＋CSP（✅ D-57 丙-9）

    @app.get("/healthz")  # 監控探針（✅ D-67 丙-13）；慣例形狀，信封豁免（06 §2.4）
    def healthz() -> dict:
        return {"status": "ok"}

    # 對話摘要：guardian 面與 admin 觀測共用同一實例。
    summaries = core.summaries
    # prefix 由此統一指定（✅ D-28 乙-4）；/api/v1 為 D-27 版本前綴。
    app.include_router(
        create_guardian_face_router(
            verifier=verifier,
            accounts=core.accounts,
            schedules=core.schedules,
            clock=clock,
            risk_events=risk_events,
            reminder_logs=core.reminder_logs,
            summaries=summaries,
        ),
        prefix="/api/v1",
    )
    app.include_router(
        create_admin_router(
            admin_api_key=settings.admin_api_key,
            traces=core.traces,
            clock=clock,
            risk_events=risk_events,
            account_store=core.account_store,
            schedule_store=core.schedule_store,
            reminder_logs=core.reminder_logs,
            summaries=summaries,
            long_term=core.long_term,
            deliveries=deliveries,
            rag_releases=PgRagReleaseStore(db),
            rag_content_policy=settings.rag_content_policy,
            opik_url_override=settings.opik_url_override,
            news=core.news,
        ),
        prefix="/api/v1/admin",
    )
    # 內測操作面（spec 2026-07-12 §3.4）：與 worker 共用同一份 job 清單。
    app.include_router(
        create_admin_jobs_router(
            admin_api_key=settings.admin_api_key,
            internal_testing_enabled=settings.internal_testing_enabled,
            jobs=build_jobs(settings, core, clock=clock),
            schedule_state=PgScheduleStateStore(db, tz),
            accounts=core.accounts,
            schedule_store=core.schedule_store,
            channel_router=core.router,
            record_reminder=core.reminder_logs.record,
            clock=clock,
        ),
        prefix="/api/v1/admin",
    )
    # 守則的逃生口：反思產出的守則自動生效，後台只能事後撤銷（無「採用」動作）。
    app.include_router(
        create_admin_strategies_router(
            admin_api_key=settings.admin_api_key,
            strategies=core.strategies,
        ),
        prefix="/api/v1/admin",
    )
    app.include_router(
        create_app_auth_router(
            accounts=core.accounts,
            rate_limiter=PgRateLimiter(
                core.db,
                settings.auth_rate_limit_max_attempts,
                settings.auth_rate_limit_window_seconds,
            ),
            notifications=core.notifications,
        ),
        prefix="/api/v1",
    )
    # App 對講機：JSON 回應固定帶文字（include_text 與 LINE 的訊息額度考量無關）。
    app.include_router(
        create_app_turns_router(
            accounts=core.accounts,
            pipeline=pipeline,
            gate=gate,
            voice=VoiceReplyDelivery(
                publisher,
                include_text=True,
                show_transcript=settings.asr_debug_show_transcript,
            ),
            traces=core.traces,
            inbound_audio=inbound_audio,
            # 地點（spec 2026-07-17）：clock 與 LocationFacts 同源（皆為本函式的 clock），
            # 否則寫入時刻與過期判斷會用到兩個不同的時鐘、讓門檻悄悄偏移。
            locations=core.locations,
            clock=clock,
            max_audio_bytes=settings.audio_max_upload_bytes,
        ),
        prefix="/api/v1",
    )
    # 公開 meta（spec 2026-07-12）：內測模式下發；App 與 admin 前端啟動時查一次。
    app.include_router(
        create_meta_router(internal_testing_enabled=settings.internal_testing_enabled),
        prefix="/api/v1",
    )
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/liff", StaticFiles(directory=dist, html=True), name="liff")
    admin_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist-admin"
    if admin_dist.is_dir():
        app.mount("/admin", StaticFiles(directory=admin_dist, html=True), name="admin")
    return app
