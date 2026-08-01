"""組裝根：把設定與各元件接成可服務的 FastAPI app。

啟動：uv run uvicorn "kinsun.app:build_app" --factory --reload
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from linebot.v3 import WebhookParser
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from kinsun import background, tracing
from kinsun.accounts.models import Channel
from kinsun.audio.publisher import build_audio_publisher
from kinsun.binding.flow import BindingFlow
from kinsun.binding.gate import AllowAllGate, ConsentGate
from kinsun.binding.session import PgBindingSessionStore
from kinsun.channels.app.admission import TurnAdmission
from kinsun.channels.app.turns import create_app_turns_router
from kinsun.channels.app.ws import create_app_ws_router
from kinsun.channels.inbound import FALLBACK_PROMPT, VoiceReplyDelivery
from kinsun.channels.line.webhook import create_app
from kinsun.composition import assemble_core, build_externals
from kinsun.config import load_dotenv, load_settings
from kinsun.cron.registry import job_specs
from kinsun.cron.state import PgScheduleStateStore
from kinsun.cron.worker import build_jobs
from kinsun.llm import build_gemini_for
from kinsun.logging_setup import setup_logging
from kinsun.pipeline import VoicePipeline
from kinsun.rag.releases import PgRagReleaseStore
from kinsun.safety.classifier import LlmRiskClassifier
from kinsun.safety.combined_classifier import LlmCombinedSafetyClassifier
from kinsun.safety.deliveries import PgRiskNotificationLogStore
from kinsun.safety.detector import RiskDetector
from kinsun.safety.moderation import AbuseModerator, LlmAbuseClassifier
from kinsun.safety.notifier import GuardianNotifier
from kinsun.schedules.flow import ScheduleMenu
from kinsun.speech.ack_audio import AckAudioCache, start_prewarm
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import build_tts_client
from kinsun.web.auth import LineIdTokenVerifier
from kinsun.web.envelope import install_error_envelope
from kinsun.web.ratelimit import PgRateLimiter, SlidingWindowRateLimiter
from kinsun.web.routers import (
    create_admin_jobs_router,
    create_admin_router,
    create_admin_strategies_router,
    create_app_auth_router,
    create_guardian_face_router,
    create_meta_router,
)
from kinsun.web.routers.demo_status import (
    create_demo_status_router,
    database_probe,
    llm_probe,
    scheduler_probe,
    service_probe,
)
from kinsun.web.security import install_security_headers

logger = logging.getLogger("kinsun.app")

# 運營狀態探針的逾時（秒）。刻意很短：這是使用者進站看到的第一個畫面，
# 不可以被一個連不上的服務拖住。
_DEMO_PROBE_TIMEOUT = 1.5


def _static_mounts(root: Path) -> list[tuple[str, Path]]:
    """回傳「掛載路徑 → 靜態目錄」清單，只含真的 build 過的。

    ⚠️ 不存在就不掛（既有行為）：部署時若前端還沒 build，整個後端不該因此起不來。
    """
    candidates = [
        ("/liff", root / "frontend" / "dist"),
        ("/admin", root / "frontend" / "dist-admin"),
        # 網頁版全功能前端（spec 2026-07-30 W-16）：與 API 同源，免 CORS。
        ("/demo", root / "web" / "dist"),
    ]
    return [(path, directory) for path, directory in candidates if directory.is_dir()]


class _SpaStaticFiles(StaticFiles):
    """單頁應用的靜態檔：找不到的路徑回 index.html，讓前端路由自己處理。

    三個前端（/liff、/admin、/demo）都是前端路由的單頁應用：網址列上的
    `/demo/stage` 這種路徑在磁碟上不存在，直接向伺服器要就是 404。使用者做的事
    完全正常——進到舞台後按重整、或把網址複製給別人——卻拿到一頁 Not Found。

    ⚠️ **只對「看起來不是資產」的路徑回退**（最後一段沒有副檔名）。全部回退的話，
    一個打錯的圖片或 JS 路徑會拿到 200 ＋ 一頁 HTML，而瀏覽器會安靜地渲染失敗
    ——那比 404 難查得多。
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def _mount_static(app: FastAPI, root: Path) -> None:
    """把 build 過的前端掛上去。三個掛載點共用同一個單頁應用回退。"""
    for mount_path, directory in _static_mounts(root):
        app.mount(
            mount_path, _SpaStaticFiles(directory=directory, html=True), name=mount_path.lstrip("/")
        )


# 危急分級脈絡窗的長度，理由見 `build_app` 裡接線處的說明。
_RISK_CONTEXT_TURNS = 6


def _recent_elder_utterances(memory) -> Callable[[str], list[str]]:
    """回傳「取這位長輩本輪之前說過的最後幾句」的函式，供危急分級當脈絡。

    抽成具名函式而非行內 lambda：它有兩個容易寫錯又測不出來的細節——只取
    `role="user"`、只取最後 `_RISK_CONTEXT_TURNS` 句——寫成 lambda 就沒有地方
    掛這段說明，也沒有地方掛測試。
    """

    def fetch(elder_id: str) -> list[str]:
        turns = memory.recent(elder_id)
        return [m.content for m in turns if m.role == "user"][-_RISK_CONTEXT_TURNS:]

    return fetch


def build_app() -> FastAPI:
    # ⚠️ 必須是第一行：在此之前發生的任何事（設定載入失敗、建表卡住）都印不出來。
    # 這個行程原本完全沒有日誌設定，39 個 kinsun.* logger 的 INFO 全數丟棄——見
    # logging_setup 的模組 docstring。
    setup_logging()
    load_dotenv()
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)

    def clock() -> datetime:
        return datetime.now(tz)

    # 背景落庫（2026-07-26 延遲實測）：觀測稽核與提醒回應標記移出長輩的回覆路徑。
    # 只有這個組裝根啟用——排程 worker 是批次作業，沒有人在等它的回覆，多一個池只是
    # 多一份連線競爭；單元測試不啟用，故行為與引入前一字不差。
    background.configure()
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
    # 分級＋審核合併成一次 Gemini 呼叫（2026-07-30 延遲優化 C2）：預設關，見
    # settings.safety_combined_classifier_enabled 的說明。單獨開合併分類器沒有
    # 意義（moderator 為 None 時管線不會用到它），故一併判斷審核是否啟用。
    combined_classifier = (
        LlmCombinedSafetyClassifier(safety_llm)
        if settings.safety_combined_classifier_enabled and settings.safety_moderation_enabled
        else None
    )
    if settings.safety_combined_classifier_enabled and not settings.safety_moderation_enabled:
        # 半開狀態靜默失效最難查（維運者以為開了）：留一行明確的 warning。
        logger.warning(
            "SAFETY_COMBINED_CLASSIFIER_ENABLED=true 但 SAFETY_MODERATION_ENABLED=false，"
            "合併分類器不會生效（合併的目的是同時省下審核那次呼叫）"
        )
    # 危急分級的脈絡窗（2026-08-01）：本輪之前、長輩自己說過的最後幾句。
    # ⚠️ 不做成環境變數：這不是維運要調的旋鈕，是安全行為的一部分——能被關掉的
    # 安全防線遲早會在某台機器上是關著的。六句夠一段完整的情緒鋪陳，又不至於把
    # 半天前不相干的話拖進來影響判定。
    # ⚠️ 只取 role="user"：金孫的安撫話術（「聽了真讓人好擔心」）帶著危急詞彙，
    # 混進去會讓分級器對著自己的回覆升級。
    # 本輪原話此刻還沒進庫（記憶由 `agent.handle` 在分級之後才寫），故不會重複。
    # TTS 分段串流（2026-07-26 延遲優化）：只對 App 通道啟用。
    # ⚠️ LINE 不可加入——它一輪只能回一則語音訊息，給它第一句等於把後面的話吞掉；
    # 分段需要投遞端「逐段拉、接著播」的配合，目前只有 App 對講機做得到。
    tts_client = build_tts_client(settings)
    pipeline = VoicePipeline(
        asr=build_asr_client(settings),
        agent=core.agent,
        tts=tts_client,
        chunked_channels=frozenset({Channel.APP.value}),
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
        # 一輪的總時間上限（辛-21）：逐次逾時攔不住三次呼叫相加。
        turn_budget_seconds=settings.turn_budget_seconds,
        moderator=moderator,
        combined_classifier=combined_classifier,
        recent_utterances=_recent_elder_utterances(core.memory),
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
    # 安撫話音檔（spec 2026-07-28 P2）：啟動時把語庫的十幾句合成上傳好，對話中只查表。
    # ⚠️ 用**獨立的 prefix**（`acks/`）：`publisher` 的 `cleanup(retention_days)` 會依
    # 日期資料夾刪除 `tts/` 下的音檔，安撫話被掃到就得重新合成。它們也沒有個資
    # （都是我們自己寫的通用句），故與長輩的回覆音檔區隔對待是合理的。
    # ⚠️ 必須排在 voice 之前（V-02，2026-07-29）：回退話術的音檔由這份快取供應。
    ack_audio = None
    if publisher is not None:
        ack_audio = AckAudioCache(
            tts_client,
            build_audio_publisher(
                settings, clock=clock, new_id=lambda: uuid.uuid4().hex, prefix="acks"
            ),
            signed_url_ttl_seconds=settings.audio_signed_url_expires_seconds,
            # 管線失敗時唸的那一句也要預錄（V-02）：走到那裡代表 ASR／LLM／記憶已經
            # 壞了一個，當場合成既慢又可能一起失敗。
            standby_phrases=(FALLBACK_PROMPT,),
        )
        # 非阻塞：十幾段 × 約 1.9 秒 ≈ 半分鐘，同步跑會把服務啟動整整擋住那麼久。
        start_prewarm(ack_audio)
    standby_clip = ack_audio.clip_for_text if ack_audio is not None else None
    voice = VoiceReplyDelivery(
        publisher,
        settings.tts_reply_text,
        show_transcript=settings.asr_debug_show_transcript,
        standby_clip=standby_clip,
    )

    def _shutdown() -> None:
        # ⚠️ 順序有意義：背景落庫必須先排空，否則佇列裡的觀測寫入會撞上已關閉的
        # 連線池，部署重啟就吃掉最後幾筆稽核。
        background.shutdown()
        # TTS 佇列同理先排空（spec 2026-07-28 P1）：關機時佇列裡可能還有長輩的回覆
        # 等著合成，直接關掉等於讓那一輪永遠沒有聲音。`close` 對未包裝的客戶端
        # （文字泡泡）不存在，故以 getattr 取用——組裝根不該假設後端型別。
        close_tts = getattr(tts_client, "close", None)
        if close_tts is not None:
            close_tts()
        db.close()

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
        on_shutdown=_shutdown,
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
            # 與 ScheduleMenu 同一個來源：回診提醒的鐘點只有一份設定。
            appointment_hour=settings.appointment_reminder_hour,
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
    # specs 是**全系統**的排程宣告（含跑在別的程序的 RAG 週更），jobs 只有本程序
    # 綁得出執行體的那些——監控要看得到全部，手動觸發只能動得了自己這一份。
    app.include_router(
        create_admin_jobs_router(
            admin_api_key=settings.admin_api_key,
            internal_testing_enabled=settings.internal_testing_enabled,
            specs=job_specs(settings),
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
            push_tokens=core.push_tokens,
        ),
        prefix="/api/v1",
    )
    # 對講機容量閘門（spec 2026-07-30 §10 B2）：POST /turns 與 WS /ws/talk 共用
    # **同一個**閘門物件——各自建一個的話，兩條路徑合計的併發可以繞過對方的上限，
    # 而 GPU 不在乎請求是從哪條路進來的。⚠️ `turn_concurrency_limit` 是**每個
    # worker 各自**的上限，實際全域上限＝本值×`WEB_WORKERS`（見 admission.py
    # 模組 docstring）。
    turn_admission = TurnAdmission(
        settings.turn_concurrency_limit,
        queue_timeout=settings.turn_queue_timeout_seconds,
    )
    # 每位長輩每分鐘的輪數保險絲：純粹防前端 bug（重連迴圈狂送），對真人操作
    # 等同無限（單進程記憶體實作，多 worker 下各進程獨立計數——與認證節流的
    # `SlidingWindowRateLimiter` 同一種前提，見 `web/ratelimit.py`）。
    turn_rate_limiter = SlidingWindowRateLimiter(settings.turn_rate_limit_per_minute, 60.0)
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
                standby_clip=standby_clip,
            ),
            traces=core.traces,
            inbound_audio=inbound_audio,
            # 地點（spec 2026-07-17）：clock 與 LocationFacts 同源（皆為本函式的 clock），
            # 否則寫入時刻與過期判斷會用到兩個不同的時鐘、讓門檻悄悄偏移。
            locations=core.locations,
            clock=clock,
            max_audio_bytes=settings.audio_max_upload_bytes,
            # 分段串流的後續段落：從長輩自己最後一則回覆重新切句、逐段合成上傳。
            memory=core.memory,
            tts=tts_client,
            audio_publisher=publisher,
            admission=turn_admission,
            rate_limiter=turn_rate_limiter,
        ),
        prefix="/api/v1",
    )
    # App 對講機的 WebSocket 通道（spec 2026-07-28 P2）：與上面的 POST /turns 平行，
    # 差別在後端可以主動送第二則訊息——先「好，我幫您查一下喔」，答案好了再送。
    # ⚠️ 整輪走同一條連線是刻意的：後端跑兩個 worker，只加下行通道會讓「算出答案的
    # worker 推不到長輩的連線」。POST /turns 保留為降級路徑，兩者共存。
    app.include_router(
        create_app_ws_router(
            accounts=core.accounts,
            pipeline=pipeline,
            gate=gate,
            voice=VoiceReplyDelivery(
                publisher,
                include_text=True,
                show_transcript=settings.asr_debug_show_transcript,
                standby_clip=standby_clip,
            ),
            traces=core.traces,
            inbound_audio=inbound_audio,
            ack_audio=ack_audio,
            locations=core.locations,
            new_id=lambda: uuid.uuid4().hex,
            clock=clock,
            max_audio_bytes=settings.audio_max_upload_bytes,
            admission=turn_admission,
            rate_limiter=turn_rate_limiter,
        ),
        prefix="/api/v1",
    )
    # 公開 meta（spec 2026-07-12）：內測模式下發；App 與 admin 前端啟動時查一次。
    app.include_router(
        create_meta_router(internal_testing_enabled=settings.internal_testing_enabled),
        prefix="/api/v1",
    )
    # 公開運營狀態（spec 2026-07-30 W-03）：網頁版前端進站即查，據此決定
    # 「開始使用」能不能按。不需認證，只回粗粒度狀態——見 demo_status.py 的說明。
    #
    # ⚠️ `settings.asr_endpoint`／`tts_endpoint` 在 backend=mock／bubble 的開發設定
    # 下是空字串，此時探針回 unknown（「這個部署沒接語音服務」），而 unknown 不影響
    # 整體可用——本機開發不該因為沒接 DGX 就進不去。
    app.include_router(
        create_demo_status_router(
            probes={
                "database": database_probe(db),
                "asr": service_probe(settings.asr_endpoint, timeout=_DEMO_PROBE_TIMEOUT),
                "tts": service_probe(settings.tts_endpoint, timeout=_DEMO_PROBE_TIMEOUT),
                "llm": llm_probe(core.traces, clock=time.time),
                "scheduler": scheduler_probe(
                    PgScheduleStateStore(db, tz), job_specs(settings), clock=clock
                ),
            }
        ),
        prefix="/api/v1",
    )
    _mount_static(app, Path(__file__).resolve().parents[2])
    return app
