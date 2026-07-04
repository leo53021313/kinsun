"""共用組裝：把設定接成兩個組裝根共用的物件圖（Core）。

分兩層：
- build_externals(settings)：接會連線的外部相依（DB / Gemini / Mem0 / LINE），含 ensure_schema。
- assemble_core(settings, externals, *, clock)：純接線組出 Core（不連網、可離線測）。

兩個組裝根（build_app / build_scheduler）都先 build_externals 再 assemble_core，
各自只補自己專屬（edge-specific）的接線。CareAgent 只在本檔建構。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from kinsun.accounts.service import AccountService
from kinsun.accounts.store import PgAccountStore
from kinsun.agent import CareAgent
from kinsun.appointments.facts import AppointmentFacts
from kinsun.appointments.service import AppointmentService
from kinsun.appointments.store import PgAppointmentStore
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.config import Settings
from kinsun.db import Database, ensure_schema
from kinsun.llm import GeminiClient, LLMClient
from kinsun.medications.facts import MedicationFacts
from kinsun.medications.service import MedicationService
from kinsun.medications.store import PgMedicationStore
from kinsun.memory.longterm.mem0_factory import build_mem0_memory
from kinsun.memory.longterm.store import Mem0LongTermStore
from kinsun.memory.recall import MemoryContext
from kinsun.memory.shortterm import PgMemoryStore
from kinsun.observability.store import PgTraceStore
from kinsun.rag.embeddings import GeminiEmbeddingModel
from kinsun.rag.retriever import HealthEducationRetriever
from kinsun.rag.service import HealthEducationRagService
from kinsun.rag.vector_store import PgVectorStore
from kinsun.reports.reminders import PgReminderLogStore
from kinsun.tools.clock import CURRENT_TIME_SPEC, build_current_time_handler
from kinsun.tools.health_rag import HEALTH_RAG_SPEC, build_health_rag_handler
from kinsun.tools.registry import ToolRegistry
from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler


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
    accounts: AccountService
    med_store: PgMedicationStore
    appt_store: PgAppointmentStore
    medications: MedicationService
    appointments: AppointmentService
    memory: PgMemoryStore
    traces: PgTraceStore
    reminder_logs: PgReminderLogStore
    agent: CareAgent


def build_externals(settings: Settings) -> Externals:
    """接外部相依：先建表，再開連線與各外部 client。會連線，不進單元測試。"""
    ensure_schema(settings.database_url)
    db = Database.open(settings.database_url)
    gemini = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
    )
    long_term = Mem0LongTermStore(build_mem0_memory(settings), top_k=settings.longterm_top_k)
    messenger = LineApiMessenger(settings.line_channel_access_token)
    return Externals(db=db, gemini=gemini, long_term=long_term, messenger=messenger)


def build_tool_registry(
    *, clock: Callable[[], datetime], rag_service: HealthEducationRagService
) -> ToolRegistry:
    """集中組工具：日後新增工具只改這裡，兩個組裝根自動都有。"""
    registry = ToolRegistry()
    registry.register(WEATHER_SPEC, build_weather_handler())
    registry.register(CURRENT_TIME_SPEC, build_current_time_handler(clock))
    registry.register(HEALTH_RAG_SPEC, build_health_rag_handler(rag_service))
    return registry


def assemble_core(
    settings: Settings, externals: Externals, *, clock: Callable[[], datetime]
) -> Core:
    """組線路：拿外部相依接出共用物件圖。純建構、不連網、可離線測。"""

    def new_id() -> str:
        return uuid.uuid4().hex

    db = externals.db
    memory = PgMemoryStore(db, clock=clock, max_turns=settings.memory_max_turns)
    accounts = AccountService(
        PgAccountStore(db),
        clock=clock,
        ttl_hours=settings.invite_ttl_hours,
        max_attempts=settings.invite_max_attempts,
    )
    med_store = PgMedicationStore(db)
    appt_store = PgAppointmentStore(db)
    medications = MedicationService(med_store)
    appointments = AppointmentService(appt_store)
    context = MemoryContext(
        externals.long_term,
        facts=[
            MedicationFacts(accounts, medications),
            AppointmentFacts(accounts, appointments, clock=clock),
        ],
    )
    rag_service = HealthEducationRagService(
        HealthEducationRetriever(
            vector_store=PgVectorStore(db),
            embedding_model=GeminiEmbeddingModel(
                api_key=settings.gemini_api_key,
                model=settings.longterm_embedding_model,
            ),
        ),
        llm=externals.gemini,
        top_k=settings.rag_top_k,
    )
    agent = CareAgent(
        externals.gemini,
        memory,
        context,
        tools=build_tool_registry(clock=clock, rag_service=rag_service),
    )
    return Core(
        settings=settings,
        db=db,
        gemini=externals.gemini,
        long_term=externals.long_term,
        messenger=externals.messenger,
        accounts=accounts,
        med_store=med_store,
        appt_store=appt_store,
        medications=medications,
        appointments=appointments,
        memory=memory,
        traces=PgTraceStore(db, clock=clock, new_id=new_id),
        reminder_logs=PgReminderLogStore(db, clock=clock, new_id=new_id),
        agent=agent,
    )
