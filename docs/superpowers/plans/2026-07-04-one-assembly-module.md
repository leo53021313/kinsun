# 單一組裝核心（One Assembly Module）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `build_app` 與 `build_scheduler` 兩個組裝根重複、且已分岐的物件圖，收斂成一個 `composition.py` 共用組裝核心（Core），兩根都改成先接外部（Externals）再組線路（Core），各自只補專屬接線。

**Architecture:** 分兩層——`build_externals(settings)` 建會連線的重量級 adapter（DB／Gemini／Mem0／LINE，含 `ensure_schema`）；`assemble_core(settings, externals, *, clock)` 純接線組出 frozen `Core`（不連網、可離線測）。工具清單由 `build_tool_registry` 集中組，未來新增工具只改一處。CareAgent 一律裝滿工具，消除「一根有工具、一根沒有」的分岐。

**Tech Stack:** Python 3、frozen `dataclass`、pytest、uv、ruff。無新增第三方套件。

## Global Constraints

- 語言：台灣繁體中文（註解、docstring、commit 訊息）。
- 命名（AGENTS.md）：construction 動詞用 `build_*`；組裝概念詞已入 `CONTEXT.md`（組裝根／外部相依 Externals／組裝核心 Core）。
- 只在 `Leo` 個人分支工作；不 push、不改寫 Git 歷史。
- OS-agnostic：`pathlib`、`ZoneInfo`；金鑰走環境變數。
- 測試：`KINSUN_IT` 保留給整合測試；本計畫新增的是**離線單元測試**，不連 DB／不連網。
- 不改任何 domain 行為；只搬動組裝位置。順手修掉的既有分岐：`MedicationFacts` 型別不一致、`AccountService` 參數不一致、clock 各寫各的。

---

## File Structure

- `src/kinsun/composition.py`（新增）— 共用組裝：`Externals`、`Core`、`build_externals`、`build_tool_registry`、`assemble_core`。唯一可 `CareAgent(...)` 的地方。
- `src/kinsun/app.py`（改）— `build_app` 改為 `build_externals` → `assemble_core` → 補 web 專屬接線（pipeline／webhook／binding／menus／routers／static）。
- `src/kinsun/scheduler/worker.py`（改）— `build_scheduler` 同樣改為消費 Core，補 scheduler 專屬接線（jobs／Scheduler／summaries）。
- `tests/test_composition.py`（新增）— 離線守門測試。

---

### Task 1: 共用組裝核心 `composition.py` ＋ 離線守門測試

建立新 seam 與其測試。**不動兩個根**，所以此時 app／worker 仍各自建圖（暫時重複，但不破壞任何東西）；整合在 Task 2、3。

**Files:**
- Create: `src/kinsun/composition.py`
- Test: `tests/test_composition.py`

**Interfaces:**
- Produces:
  - `class Externals(db, gemini, long_term, messenger)` — frozen dataclass。
  - `class Core(settings, db, gemini, long_term, messenger, accounts, med_store, appt_store, medications, appointments, memory, traces, reminder_logs, agent)` — frozen dataclass。
  - `build_externals(settings: Settings) -> Externals`
  - `build_tool_registry(*, clock: Callable[[], datetime], rag_service: HealthEducationRagService) -> ToolRegistry`
  - `assemble_core(settings: Settings, externals: Externals, *, clock: Callable[[], datetime]) -> Core`

- [ ] **Step 1: 寫失敗測試 `tests/test_composition.py`**

```python
"""composition 的離線守門測試：不連 DB、不連網。

刻意檢視 CareAgent／MemoryContext 內部欄位（`_tools`／`_context`／`_facts`）——
這是「組裝形狀」的結構性守門，用來擋掉兩個組裝根再度分岐。
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.appointments.facts import AppointmentFacts
from kinsun.composition import Externals, assemble_core, build_tool_registry
from kinsun.config import load_settings
from kinsun.medications.facts import MedicationFacts
from kinsun.tools.clock import CURRENT_TIME_SPEC
from kinsun.tools.health_rag import HEALTH_RAG_SPEC
from kinsun.tools.weather import WEATHER_SPEC

_ENV = {
    "LINE_CHANNEL_SECRET": "secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "token",
    "GEMINI_API_KEY": "key",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}


def _clock() -> datetime:
    return datetime(2026, 7, 4, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _fake_externals() -> Externals:
    # 組線路階段不呼叫這些外部相依，傳 sentinel 即可（純結構測試）。
    return Externals(db=object(), gemini=object(), long_term=object(), messenger=object())


def _core():
    return assemble_core(load_settings(_ENV), _fake_externals(), clock=_clock)


def test_assemble_core_agent_has_all_three_tools():
    core = _core()
    names = {spec.name for spec in core.agent._tools.specs()}
    assert names == {WEATHER_SPEC.name, CURRENT_TIME_SPEC.name, HEALTH_RAG_SPEC.name}


def test_assemble_core_injects_two_fact_providers_in_order():
    core = _core()
    facts = core.agent._context._facts
    assert [type(f) for f in facts] == [MedicationFacts, AppointmentFacts]


def test_build_tool_registry_registers_three_tools():
    registry = build_tool_registry(clock=_clock, rag_service=object())
    assert len(registry.specs()) == 3
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `PYTHONPATH=src uv run pytest tests/test_composition.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'kinsun.composition'`

- [ ] **Step 3: 建立 `src/kinsun/composition.py`**

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `PYTHONPATH=src uv run pytest tests/test_composition.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: ruff 檢查新檔**

Run: `uv run ruff check src/kinsun/composition.py tests/test_composition.py`
Expected: All checks passed!

- [ ] **Step 6: Commit**

```bash
git add src/kinsun/composition.py tests/test_composition.py
git commit -m "feat: 新增共用組裝核心 composition（Externals/Core/assemble_core）與離線守門測試"
```

---

### Task 2: `build_app` 改為消費 Core

**Files:**
- Modify: `src/kinsun/app.py`（整檔重寫 `build_app` 與 import 區）

**Interfaces:**
- Consumes: `build_externals`、`assemble_core`（Task 1）。使用 `core.agent / core.gemini / core.accounts / core.messenger / core.medications / core.appointments / core.traces / core.reminder_logs / core.db`。

- [ ] **Step 1: 以下列內容整檔覆寫 `src/kinsun/app.py`**

```python
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
from kinsun.safety.notifier import LineGuardianNotifier
from kinsun.speech.asr import build_asr_client
from kinsun.speech.tts import build_tts_client
from kinsun.web.admin_api import create_admin_api_router
from kinsun.web.api import create_api_router
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
        notifier=LineGuardianNotifier(core.accounts, core.messenger),
        risk_events=risk_events,
        traces=core.traces,
        model_name=settings.gemini_model,
    )
    binding_sessions = PgBindingSessionStore(db)
    medication_menu = MedicationMenu(
        core.medications, core.accounts, binding_sessions, clock=clock
    )
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
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/liff", StaticFiles(directory=dist, html=True), name="liff")
    admin_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist-admin"
    if admin_dist.is_dir():
        app.mount("/admin", StaticFiles(directory=admin_dist, html=True), name="admin")
    return app
```

- [ ] **Step 2: import 能載入、ruff 乾淨**

Run: `PYTHONPATH=src uv run python -c "import kinsun.app"` （只 import 模組，不呼叫 build_app，不連線）
Expected: 無輸出、exit 0

Run: `uv run ruff check src/kinsun/app.py`
Expected: All checks passed!（若有 F401 未用 import，依提示刪除）

- [ ] **Step 3: 全套件測試仍綠**

Run: `PYTHONPATH=src uv run pytest -q`
Expected: PASS（沿用既有數量；不應有新失敗）

- [ ] **Step 4: Commit**

```bash
git add src/kinsun/app.py
git commit -m "refactor: build_app 改為消費共用組裝核心 Core，移除重複建圖"
```

---

### Task 3: `build_scheduler` 改為消費 Core ＋ 加上「CareAgent 只准一處」守門測試

**Files:**
- Modify: `src/kinsun/scheduler/worker.py`（重寫 `build_scheduler` 與 import 區；`serve`／`main` 不變）
- Modify: `tests/test_composition.py`（新增來源守門測試）

**Interfaces:**
- Consumes: `build_externals`、`assemble_core`（Task 1）。使用 `core.memory / core.long_term / core.gemini / core.accounts / core.med_store / core.appt_store / core.appointments / core.reminder_logs / core.agent / core.messenger / core.traces / core.db`。

- [ ] **Step 1: 以下列內容整檔覆寫 `src/kinsun/scheduler/worker.py`**

```python
"""排程 worker：長跑迴圈，定時 run_due。

CLI：PYTHONPATH=src uv run python -m kinsun.scheduler
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.audio.publisher import build_audio_publisher
from kinsun.composition import assemble_core, build_externals
from kinsun.config import Settings, load_dotenv, load_settings
from kinsun.db import Database
from kinsun.medications.jobs import build_medication_slot_job
from kinsun.medications.models import MedicationSlot
from kinsun.memory.longterm.consolidation import run_consolidation
from kinsun.observability.jobs import build_observability_cleanup_job
from kinsun.proactive.jobs import (
    GREETING_INTENT,
    INACTIVITY_INTENT,
    build_greeting_job,
    build_inactivity_job,
)
from kinsun.reports.reminders import safe_record
from kinsun.reports.summaries import PgConversationSummaryStore, summarize_day
from kinsun.scheduler.jobs import build_audio_cleanup_job, build_consolidation_job
from kinsun.scheduler.scheduler import Scheduler
from kinsun.scheduler.state import PgScheduleStateStore

logger = logging.getLogger("kinsun.scheduler.worker")


def build_scheduler(
    settings: Settings, *, clock: Callable[[], datetime]
) -> tuple[Scheduler, Database]:
    tz = ZoneInfo(settings.timezone)
    externals = build_externals(settings)
    core = assemble_core(settings, externals, clock=clock)
    db = core.db
    memory = core.memory
    long_term = core.long_term
    gemini = core.gemini
    accounts = core.accounts
    med_store = core.med_store
    appt_store = core.appt_store
    appointments = core.appointments
    reminder_logs = core.reminder_logs
    agent = core.agent
    messenger = core.messenger
    traces = core.traces
    summaries = PgConversationSummaryStore(db, clock=clock)

    def _record_push(line_user_id: str, kind: str, content: str) -> None:
        # 主動推播補記 reminder_logs：查得到綁定長輩才記（觀測用，失敗不影響推播）。
        elder = accounts.elder_by_line(line_user_id)
        if elder is not None:
            safe_record(reminder_logs.record, elder.elder_id, kind, content)

    def run_one(line_user_id: str) -> None:
        run_consolidation(line_user_id, short_term=memory, long_term=long_term)
        try:
            summarize_day(
                line_user_id,
                short_term=memory,
                summarizer=gemini,
                summaries=summaries,
                clock=clock,
            )
        except Exception:  # noqa: BLE001 - 摘要失敗不影響整理與其他長輩
            logger.warning("對話摘要失敗 session=%s", line_user_id)

    def greet_one(line_user_id: str) -> None:
        content = agent.proactive(line_user_id, GREETING_INTENT)
        messenger.push_text(line_user_id, content)
        _record_push(line_user_id, "proactive-greeting", content)

    def care_one(line_user_id: str) -> None:
        content = agent.proactive(line_user_id, INACTIVITY_INTENT)
        messenger.push_text(line_user_id, content)
        _record_push(line_user_id, "proactive-care", content)

    jobs = [
        build_consolidation_job(
            sessions=memory.sessions,
            run_one=run_one,
            hour=settings.longterm_consolidation_hour,
        ),
        build_greeting_job(
            sessions=memory.sessions, greet_one=greet_one, hour=settings.proactive_greeting_hour
        ),
        build_inactivity_job(
            sessions=memory.sessions,
            last_active=memory.last_active,
            clock=clock,
            threshold_seconds=settings.proactive_inactivity_days * 86400,
            care_one=care_one,
            hour=settings.proactive_inactivity_hour,
        ),
    ]
    med_slots = [
        (MedicationSlot.MORNING, settings.medication_morning_hour, "medication-morning"),
        (MedicationSlot.NOON, settings.medication_noon_hour, "medication-noon"),
        (MedicationSlot.EVENING, settings.medication_evening_hour, "medication-evening"),
        (MedicationSlot.BEDTIME, settings.medication_bedtime_hour, "medication-bedtime"),
    ]
    for slot, hour, name in med_slots:
        jobs.append(
            build_medication_slot_job(
                slot=slot,
                meds_at_slot=lambda s=slot: med_store.list_for_slot(s),
                lookup_elder=accounts.get_elder,
                is_consented_elder=accounts.is_consented_elder,
                push=messenger.push_text,
                hour=hour,
                name=name,
                record=reminder_logs.record,
            )
        )
    jobs.append(
        build_appointment_reminder_job(
            appts_on=appt_store.list_for_date,
            today=lambda: clock().date().isoformat(),
            tomorrow=lambda: (clock().date() + timedelta(days=1)).isoformat(),
            lookup_elder=accounts.get_elder,
            is_consented_elder=accounts.is_consented_elder,
            guardian_line_ids=accounts.guardian_line_ids_of_elder,
            push=messenger.push_text,
            hour=settings.appointment_reminder_hour,
            record=reminder_logs.record,
        )
    )
    if settings.tts_backend == "dgx":
        publisher = build_audio_publisher(settings, clock=clock, new_id=lambda: uuid.uuid4().hex)
        jobs.append(
            build_audio_cleanup_job(
                cleanup=lambda: publisher.cleanup(retention_days=settings.audio_retention_days),
                hour=settings.longterm_consolidation_hour,
            )
        )
    jobs.append(
        build_observability_cleanup_job(
            purge=lambda: traces.purge_older_than(
                clock().timestamp() - settings.admin_retention_days * 86400
            ),
            hour=settings.longterm_consolidation_hour,
        )
    )
    # 進站音檔與 TTS 音檔同樣走過期清理；有 Supabase 憑證即啟用。
    if settings.supabase_url and settings.supabase_service_key:
        inbound_audio = build_audio_publisher(
            settings, clock=clock, new_id=lambda: uuid.uuid4().hex, prefix="inbound"
        )
        jobs.append(
            build_audio_cleanup_job(
                cleanup=lambda: inbound_audio.cleanup(retention_days=settings.audio_retention_days),
                hour=settings.longterm_consolidation_hour,
                name="inbound-audio-cleanup",
            )
        )
    state = PgScheduleStateStore(db, tz)
    return Scheduler(jobs, clock, state), db


def serve(scheduler: Scheduler, *, tick_seconds: int) -> None:
    while True:
        scheduler.run_due()
        time.sleep(tick_seconds)


def main() -> int:
    load_dotenv()
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    scheduler, db = build_scheduler(settings, clock=lambda: datetime.now(tz))
    print(
        f"排程器啟動：每 {settings.scheduler_tick_seconds}s 檢查；"
        f"整理 {settings.longterm_consolidation_hour}:00、"
        f"問候 {settings.proactive_greeting_hour}:00、"
        f"失聯關心 {settings.proactive_inactivity_hour}:00"
        f"（{settings.proactive_inactivity_days} 天門檻）。"
    )
    try:
        serve(scheduler, tick_seconds=settings.scheduler_tick_seconds)
    finally:
        db.close()
    return 0
```

- [ ] **Step 2: 新增來源守門測試（附加到 `tests/test_composition.py` 末端）**

```python
def test_care_agent_constructed_only_in_composition():
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "kinsun"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "CareAgent(" in path.read_text(encoding="utf-8") and path.name != "composition.py"
    ]
    assert offenders == [], f"CareAgent 只能在 composition.py 建構，違規：{offenders}"
```

- [ ] **Step 3: 跑守門測試確認通過（兩根都已改完，不再有 `CareAgent(`）**

Run: `PYTHONPATH=src uv run pytest tests/test_composition.py -q`
Expected: PASS（4 passed）

- [ ] **Step 4: import 能載入、ruff 乾淨、全套件綠**

Run: `PYTHONPATH=src uv run python -c "import kinsun.scheduler.worker"`
Expected: 無輸出、exit 0

Run: `uv run ruff check src/kinsun/scheduler/worker.py`
Expected: All checks passed!

Run: `PYTHONPATH=src uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kinsun/scheduler/worker.py tests/test_composition.py
git commit -m "refactor: build_scheduler 改為消費 Core，加上 CareAgent 單一建構守門測試"
```

---

## Self-Review

**1. Spec coverage（對照 grilling 定案）：**
- 寬核心（Q1）→ `Core` 收整張共用圖 ✓
- AI 核心一律裝滿工具、工具集中組（Q2）→ `build_tool_registry` + `assemble_core` 一律帶 tools ✓
- 拆兩層、組線路可離線測（Q3）→ `build_externals` / `assemble_core` + `test_composition.py` sentinel 測試 ✓
- 守門標準（Q4）→ 三工具測試、兩 FactProvider 測試、`CareAgent(` 單一來源測試 ✓
- 命名／placement（Q5）→ `composition.py`、`build_externals`／`assemble_core`、入口不改名、`CONTEXT.md` 已加詞 ✓
- 順手修：`MedicationFacts` 一律吃 `MedicationService`、`AccountService` 一律帶 `ttl_hours/max_attempts`、clock 單一注入 ✓

**2. Placeholder scan：** 無 TBD／TODO；每個 code step 皆為完整可執行內容。

**3. Type consistency：** `Core`／`Externals` 欄位名在三個 Task 一致；`assemble_core(settings, externals, *, clock)`、`build_tool_registry(*, clock, rag_service)` 全程一致；`core.med_store`（raw store，供 scheduler 的 `list_for_slot`／`list_for_date`）與 `core.medications`／`core.appointments`（service，供 web CRUD 與 facts）刻意並存，皆有被消費。

**注意事項（實作時留意）：**
- ruff `F401`：兩根重寫後會有大量未用 import；上面的 import 區已是最終版，照覆寫即可，若 ruff 仍報再刪。
- `build_scheduler` 行為微調：scheduler 的 `accounts` 現在會帶 `invite_ttl_hours/max_attempts`（原本用預設）——scheduler 不兌換邀請碼，無行為影響、且更一致。
- 全套件測試（`pytest -q`）中連 Postgres 的整合測試需 `KINSUN_IT=1` 才會實跑；未設時會 skip，屬正常。
