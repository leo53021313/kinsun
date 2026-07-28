"""共用組裝：把設定接成兩個組裝根共用的物件圖（Core）。

分兩層：
- build_externals(settings)：接會連線的外部相依（DB / Gemini / Mem0 / LINE），含 ensure_schema。
- assemble_core(settings, externals, *, clock)：純接線組出 Core（不連網、可離線測）。

兩個組裝根（build_app / build_scheduler）都先 build_externals 再 assemble_core，
各自只補自己專屬（edge-specific）的接線。CareAgent 只在本檔建構。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from kinsun import tracing
from kinsun.accounts.facts import ElderProfileFacts
from kinsun.accounts.models import Channel
from kinsun.accounts.service import AccountService
from kinsun.accounts.store import PgAccountStore
from kinsun.agent import SYSTEM_PROMPT, CareAgent
from kinsun.channels.app.outbound import AppOutboundChannel
from kinsun.channels.line.messenger import LineApiMessenger, LineOutboundChannel
from kinsun.channels.router import ChannelRouter
from kinsun.clock import TimeFacts
from kinsun.config import Settings
from kinsun.db import Database, ensure_schema
from kinsun.llm import GeminiClient, LLMClient
from kinsun.locations.facts import LocationFacts
from kinsun.locations.store import LocationStore, PgLocationStore
from kinsun.memory.longterm.mem0_factory import build_mem0_memory
from kinsun.memory.longterm.store import Mem0LongTermStore
from kinsun.memory.recall import SessionMemory
from kinsun.memory.shortterm import PgMemoryStore
from kinsun.news.mentions import NewsMentionStore, PgNewsMentionStore
from kinsun.news.store import NewsStore, PgNewsStore
from kinsun.notifications.store import PgAppNotificationStore
from kinsun.observability.store import PgTraceStore
from kinsun.places.store import PgPlaceStore, PlaceStore
from kinsun.proactive.preferences import PgGreetingPreferenceStore
from kinsun.rag.embeddings import GeminiEmbeddingModel
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.service import HealthEducationRagService
from kinsun.rag.vector_store import PgVectorStore
from kinsun.reports.reminders import PgReminderLogStore
from kinsun.reports.summaries import PgConversationSummaryStore
from kinsun.safety.events import PgRiskEventStore
from kinsun.schedules.facts import ScheduleFacts
from kinsun.schedules.models import ScheduleKind
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import PgScheduleStore
from kinsun.strategies.facts import StrategyFacts
from kinsun.strategies.store import PgStrategyStore
from kinsun.tools.health_rag import HEALTH_RAG_SPEC, build_health_rag_handler
from kinsun.tools.lookups import PgWebSearchLookupStore, WebSearchLookupStore
from kinsun.tools.news import (
    NEWS_DETAIL_SPEC,
    NEWS_SPEC,
    build_news_detail_handler,
    build_news_handler,
)
from kinsun.tools.places import NEARBY_SPEC, build_nearby_handler
from kinsun.tools.registry import ToolRegistry
from kinsun.tools.schedules import (
    CANCEL_SPEC,
    CREATE_SPEC,
    LIST_SPEC,
    build_cancel_handler,
    build_create_handler,
    build_list_handler,
)
from kinsun.tools.transport import (
    BUS_ARRIVAL_SPEC,
    MRT_LINE_SPEC,
    PARKING_SPEC,
    ROUTE_SPEC,
    build_bus_arrival_handler,
    build_mrt_line_handler,
    build_parking_handler,
    build_route_handler,
    geocode,
)
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler
from kinsun.tools.web_search import WEB_SEARCH_SPEC, build_web_search_handler
from kinsun.transport import HttpxTransport

logger = logging.getLogger("kinsun.composition")

# ── 提示詞／註冊表對帳（2026-07-28）──
#
# 提示詞點名了工具、工具卻沒註冊時，模型不會說「我沒有這個工具」，而是假裝呼叫、
# 吐出無限重複的 `tool_code {...}`（2026-07-26 實測單則 186,514 字）。出站護欄
# （`agent._speakable`）擋得住送出去的那一坨，但長輩那一輪還是白問了——
# 真正該做的是讓這種組態在**部署當下**就被看見，而不是等長輩踩到。
#
# ⚠️ 只警告、不讓啟動失敗：優雅降級是刻意的設計（沒有 TDX 憑證仍要能跑）。
AUDITED_SPECS = (
    WEATHER_SPEC,
    HEALTH_RAG_SPEC,
    ROUTE_SPEC,
    BUS_ARRIVAL_SPEC,
    MRT_LINE_SPEC,
    PARKING_SPEC,
    WEB_SEARCH_SPEC,
    NEWS_SPEC,
    NEWS_DETAIL_SPEC,
    NEARBY_SPEC,
    CREATE_SPEC,
    LIST_SPEC,
    CANCEL_SPEC,
)
# 提示詞只用文字描述、沒有寫出工具名的那些（「用對應的交通工具查詢」）——字面掃描
# 掃不到，故明列。它們同樣是條件式註冊（TDX 憑證未齊就跳過），漏掉等於留著同一顆雷。
_PROMPT_IMPLIED_TOOLS = frozenset({BUS_ARRIVAL_SPEC.name, MRT_LINE_SPEC.name, PARKING_SPEC.name})


def list_unregistered_prompt_tools(registry: ToolRegistry) -> list[str]:
    """提示詞叫模型用、註冊表卻沒有的工具名。

    工具名由 `SYSTEM_PROMPT` 字面掃描得出，不手寫清單——日後改提示詞或加工具都自動跟上。
    """
    registered = {spec.name for spec in registry.specs()}
    named = {spec.name for spec in AUDITED_SPECS if spec.name in SYSTEM_PROMPT}
    return sorted((named | _PROMPT_IMPLIED_TOOLS) - registered)


@dataclass(frozen=True)
class Externals:
    """會連線／需真金鑰的重量級 adapter；由 build_externals 建一次。"""

    db: Database
    gemini: LLMClient
    long_term: Mem0LongTermStore
    messenger: LineApiMessenger


@dataclass(frozen=True)
class Core:
    """兩個組裝根共用的物件圖。root-specific 的 pipeline／jobs 不在此。"""

    settings: Settings
    db: Database
    gemini: LLMClient
    long_term: Mem0LongTermStore
    messenger: LineApiMessenger
    router: ChannelRouter
    account_store: PgAccountStore
    accounts: AccountService
    # 統一排程（D-76）：派送 job、對話注入、家屬 API 與長輩語音工具共用同一組。
    schedule_store: PgScheduleStore
    schedules: ScheduleService
    memory: PgMemoryStore
    traces: PgTraceStore
    reminder_logs: PgReminderLogStore
    # 兩根共用收進 Core（✅ 庚-44／A-57）：先前 app.py 與 worker 各自 new，
    # clock／new_id 接線不一致的風險就此消除。
    risk_events: PgRiskEventStore
    summaries: PgConversationSummaryStore
    notifications: PgAppNotificationStore
    # 反思寫入（worker）與後台檢視／撤銷都需要同一個 store，故收進 Core。
    strategies: PgStrategyStore
    # 收進 Core 而非讓組裝根各自 new：clock 必須與 LocationFacts 同源，否則寫入
    # 時刻與過期判斷會用到兩個不同的時鐘（庚-44／A-57 已為 risk_events 踩過此坑）。
    locations: PgLocationStore
    # 夜間批次寫、問候 job 讀（spec 2026-07-16），同一根內兩處共用，故收進 Core。
    greeting_prefs: PgGreetingPreferenceStore
    # 話題新聞（spec 2026-07-20）：worker 爬取／清除寫、問候 job 讀，同一根內兩處共用。
    news: PgNewsStore
    # 新聞提及紀錄（D-74 消費端）：get_news 工具寫、worker 清理 job 清，兩處共用。
    news_mentions: PgNewsMentionStore
    agent: CareAgent


def build_externals(settings: Settings) -> Externals:
    """接外部相依：先建表，再開連線與各外部 client。會連線，不進單元測試。"""
    # 工程觀測開關在最前面決定（configure 只設環境變數與旗標，不連線）。
    tracing.configure(settings)
    ensure_schema(settings.database_url)
    db = Database.open(settings.database_url, max_size=settings.database_pool_max_size)
    gemini = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
        client_wrapper=tracing.wrap_genai,
    )
    long_term = Mem0LongTermStore(
        build_mem0_memory(settings),
        top_k=settings.longterm_top_k,
        health_top_k=settings.longterm_health_top_k,
    )
    messenger = LineApiMessenger(settings.line_channel_access_token)
    return Externals(db=db, gemini=gemini, long_term=long_term, messenger=messenger)


def build_tool_registry(
    *,
    clock: Callable[[], datetime],
    rag_service: HealthEducationRagService,
    tavily_api_key: str = "",
    tdx_client_id: str = "",
    tdx_client_secret: str = "",
    lookups: WebSearchLookupStore | None = None,
    traces: PgTraceStore | None = None,
    news: NewsStore | None = None,
    news_mentions: NewsMentionStore | None = None,
    news_locations: PgLocationStore | None = None,
    news_blocked_keywords: str = "",
    schedules: ScheduleService | None = None,
    places: PlaceStore | None = None,
    locations: LocationStore | None = None,
    # 與 LocationFacts 共用同一個設定值；此預設鏡射 .env.example 的
    # LOCATION_STALE_AFTER_HOURS=2，正式組裝一律由 settings 明確傳入。
    location_stale_after_hours: int = 2,
) -> ToolRegistry:
    """集中組工具：日後新增工具只改這裡，兩個組裝根自動都有。"""
    registry = ToolRegistry()
    registry.register(WEATHER_SPEC, build_weather_handler())
    # 排程工具（D-76 P4）：有 service 才註冊；正式組裝一律有。全庫第一組會寫庫的
    # 工具，對象只認 ToolInvocationContext（見 tools/schedules.py 的三條界線）。
    if schedules is not None:
        registry.register(CREATE_SPEC, build_create_handler(schedules, clock=clock))
        registry.register(LIST_SPEC, build_list_handler(schedules, clock=clock))
        registry.register(CANCEL_SPEC, build_cancel_handler(schedules))
    # 時間沒有工具（2026-07-25）：get_current_time 已改為每輪注入情境（clock.TimeFacts）。
    # 話題新聞消費端（D-74 後續）：有 store 才註冊；正式組裝一律有。
    # mentions 供不重複給料、locations 供在地化加權、blocked 供負面過濾——
    # 三者皆選配，未提供時工具照常運作。
    if news is not None:
        registry.register(
            NEWS_SPEC,
            build_news_handler(
                news,
                clock=clock,
                mentions=news_mentions,
                locations=news_locations,
                blocked_keywords=news_blocked_keywords,
            ),
        )
        registry.register(
            NEWS_DETAIL_SPEC,
            build_news_detail_handler(
                news,
                clock=clock,
                mentions=news_mentions,
                blocked_keywords=news_blocked_keywords,
            ),
        )
    registry.register(
        HEALTH_RAG_SPEC,
        build_health_rag_handler(rag_service, traces=traces),
    )
    # 路線走免金鑰的 OSRM，永遠註冊。
    registry.register(ROUTE_SPEC, build_route_handler())
    # 附近地點（spec 2026-07-27）：兩個 store 都有才註冊——沒有位置就查不了「附近」，
    # 註冊一個永遠回「不知道你在哪」的工具只會浪費模型的迭代。
    if places is not None and locations is not None:
        # 地名 → 座標沿用 transport.py 既有的 Nominatim 路徑，不另接服務；比照
        # build_route_handler 的慣例只在組裝時建一次 HttpxTransport，不讓每次呼叫
        # 都新建、浪費連線池。
        places_transport = HttpxTransport()
        registry.register(
            NEARBY_SPEC,
            build_nearby_handler(
                places,
                locations,
                clock=lambda: clock().timestamp(),
                stale_after_hours=location_stale_after_hours,
                resolve_place=lambda q: geocode(places_transport, q),
            ),
        )
    # 金鑰未設＝跳過註冊（優雅降級）：金孫少一個上網查證能力，其餘功能照常運作。
    if tavily_api_key:
        registry.register(WEB_SEARCH_SPEC, build_web_search_handler(tavily_api_key, lookups))
    # TDX 憑證未齊＝跳過公車／捷運／停車工具（優雅降級）；路線工具不受影響。
    if tdx_client_id and tdx_client_secret:
        registry.register(
            BUS_ARRIVAL_SPEC, build_bus_arrival_handler(tdx_client_id, tdx_client_secret)
        )
        registry.register(MRT_LINE_SPEC, build_mrt_line_handler(tdx_client_id, tdx_client_secret))
        registry.register(PARKING_SPEC, build_parking_handler(tdx_client_id, tdx_client_secret))
    missing = list_unregistered_prompt_tools(registry)
    if missing:
        logger.warning(
            "提示詞叫金孫用這些工具、但它們沒有註冊：%s。"
            "模型會假裝呼叫並吐出無限重複的工具語法（出站護欄會攔成回退話術，"
            "但長輩那一輪等於白問）。請補上對應的金鑰或 store。",
            "、".join(missing),
        )
    return registry


def assemble_core(
    settings: Settings, externals: Externals, *, clock: Callable[[], datetime]
) -> Core:
    """組線路：拿外部相依接出共用物件圖。純建構、不連網、可離線測。"""

    def new_id() -> str:
        return uuid.uuid4().hex

    db = externals.db
    memory = PgMemoryStore(db, clock=clock, max_turns=settings.memory_max_turns)
    account_store = PgAccountStore(db)
    accounts = AccountService(
        account_store,
        clock=clock,
        ttl_hours=settings.invite_ttl_hours,
        max_attempts=settings.invite_max_attempts,
    )
    schedule_store = PgScheduleStore(db)
    schedules = ScheduleService(
        schedule_store,
        clock=clock,
        new_id=new_id,
        max_active_per_elder=settings.schedule_max_active_per_elder,
        max_days_ahead=settings.schedule_max_days_ahead,
    )
    strategies = PgStrategyStore(db, clock=clock, new_id=new_id)
    locations = PgLocationStore(db)
    # 附近地點（spec 2026-07-27）：search_nearby_places 工具讀，與 LocationFacts
    # 共用同一個 locations、不另開連線。
    places = PgPlaceStore(db)
    session = SessionMemory(
        memory,
        externals.long_term,
        facts=[
            # 時間排最前（2026-07-25）：它是其他事實的座標系——回診那行印的是絕對日期
            # 「2026-07-30」，模型不知道今天幾號就算不出剩幾天。原為 get_current_time
            # 工具，但工具是「模型想到才呼叫」，時間卻是每輪都用得到的東西。
            TimeFacts(clock=clock),
            # 稱呼緊接其後（2026-07-17）：沒有它，模型每輪亂猜「阿公／阿嬤」，
            # 真實使用一半機率叫錯；稱呼是所有段落裡最先要對的事。
            ElderProfileFacts(account_store),
            # 統一排程取代舊的用藥／回診兩段（D-76 P2）：三種 kind 各成一段，段落
            # 標題逐字沿用舊 facts（見 schedules/facts.py），prompt 因此零變動；
            # 第三段是全新的——長輩自己交代要提醒的事，金孫先前完全看不到。
            ScheduleFacts(schedule_store, kind=ScheduleKind.MEDICATION, clock=clock),
            ScheduleFacts(schedule_store, kind=ScheduleKind.APPOINTMENT, clock=clock),
            ScheduleFacts(schedule_store, kind=ScheduleKind.CUSTOM, clock=clock),
            # 閉環的最後一哩：反思學到的守則由此進入下一輪對話的 system prompt。
            StrategyFacts(strategies, max_strategies=settings.reflection_max_strategies),
            # 地點注入（spec 2026-07-17）：位置是線索不是答案，措辭見 locations/facts.py。
            # 排最後＝ prompt 中的段落順序最後：位置是這幾段裡最不重要的一段。
            LocationFacts(
                locations,
                clock=clock,
                stale_after_hours=settings.location_stale_after_hours,
            ),
        ],
    )
    rag_service = HealthEducationRagService(
        HealthEducationRetriever(
            vector_store=PgVectorStore(db),
            embedding_model=GeminiEmbeddingModel(
                api_key=settings.gemini_api_key,
                model=settings.rag_embedding_model,
                request_timeout_seconds=settings.gemini_timeout_seconds,
            ),
        ),
        llm=externals.gemini,
        top_k=settings.rag_top_k,
    )
    traces = PgTraceStore(db, clock=clock, new_id=new_id)
    web_search_lookups = PgWebSearchLookupStore(db, clock=clock, new_id=new_id)
    # 話題新聞 store：worker 爬取寫、問候與 get_news 工具讀——提前建立、兩處共用。
    news = PgNewsStore(db)
    news_mentions = PgNewsMentionStore(db)
    agent = CareAgent(
        externals.gemini,
        session,
        tools=build_tool_registry(
            clock=clock,
            rag_service=rag_service,
            tavily_api_key=settings.tavily_api_key,
            tdx_client_id=settings.tdx_client_id,
            tdx_client_secret=settings.tdx_client_secret,
            lookups=web_search_lookups,
            traces=traces,
            news=news,
            news_mentions=news_mentions,
            news_locations=locations,
            news_blocked_keywords=settings.news_blocked_keywords,
            schedules=schedules,
            places=places,
            locations=locations,
            location_stale_after_hours=settings.location_stale_after_hours,
        ),
    )
    notifications = PgAppNotificationStore(db, clock=clock, new_id=new_id)
    risk_events = PgRiskEventStore(db, clock=clock, new_id=lambda: uuid.uuid4().hex)
    summaries = PgConversationSummaryStore(db, clock=clock)
    return Core(
        settings=settings,
        db=db,
        gemini=externals.gemini,
        long_term=externals.long_term,
        messenger=externals.messenger,
        # App 出站 adapter（✅ D-12，甲-6）：訊息落 app_notifications，App 端拉取。
        router=ChannelRouter(
            account_store,
            {
                Channel.LINE: LineOutboundChannel(externals.messenger),
                Channel.APP: AppOutboundChannel(notifications),
            },
        ),
        account_store=account_store,
        accounts=accounts,
        schedule_store=schedule_store,
        schedules=schedules,
        memory=memory,
        risk_events=risk_events,
        summaries=summaries,
        traces=traces,
        reminder_logs=PgReminderLogStore(db, clock=clock, new_id=new_id),
        notifications=notifications,
        strategies=strategies,
        locations=locations,
        greeting_prefs=PgGreetingPreferenceStore(db),
        news=news,
        news_mentions=news_mentions,
        agent=agent,
    )
