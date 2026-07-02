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

from kinsun.accounts.service import AccountService
from kinsun.accounts.store import PgAccountStore
from kinsun.agent import CareAgent
from kinsun.appointments.facts import AppointmentFacts
from kinsun.appointments.jobs import build_appointment_reminder_job
from kinsun.appointments.service import AppointmentService
from kinsun.appointments.store import PgAppointmentStore
from kinsun.audio.publisher import build_audio_publisher
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.config import Settings, load_dotenv, load_settings
from kinsun.db import Database, ensure_schema
from kinsun.llm import GeminiClient
from kinsun.medications.facts import MedicationFacts
from kinsun.medications.jobs import build_medication_slot_job
from kinsun.medications.models import MedicationSlot
from kinsun.medications.store import PgMedicationStore
from kinsun.memory.longterm.consolidation import run_consolidation
from kinsun.memory.longterm.mem0_factory import build_mem0_memory
from kinsun.memory.longterm.store import Mem0LongTermStore
from kinsun.memory.recall import MemoryContext
from kinsun.memory.shortterm import PgMemoryStore
from kinsun.proactive.jobs import (
    GREETING_INTENT,
    INACTIVITY_INTENT,
    build_greeting_job,
    build_inactivity_job,
)
from kinsun.reports.reminders import PgReminderLogStore
from kinsun.reports.summaries import PgConversationSummaryStore, summarize_day
from kinsun.scheduler.jobs import build_audio_cleanup_job, build_consolidation_job
from kinsun.scheduler.scheduler import Scheduler
from kinsun.scheduler.state import PgScheduleStateStore

logger = logging.getLogger("kinsun.scheduler.worker")


def build_scheduler(
    settings: Settings, *, clock: Callable[[], datetime]
) -> tuple[Scheduler, Database]:
    tz = ZoneInfo(settings.timezone)
    ensure_schema(settings.database_url)
    db = Database.open(settings.database_url)
    memory = PgMemoryStore(
        db,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    gemini = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout_seconds,
    )
    long_term = Mem0LongTermStore(build_mem0_memory(settings), top_k=settings.longterm_top_k)
    accounts = AccountService(PgAccountStore(db), clock=clock)
    med_store = PgMedicationStore(db)
    appt_store = PgAppointmentStore(db)
    appointments = AppointmentService(appt_store)
    reminder_logs = PgReminderLogStore(db, clock=clock, new_id=lambda: uuid.uuid4().hex)
    summaries = PgConversationSummaryStore(db, clock=clock)
    context = MemoryContext(
        long_term,
        facts=[
            MedicationFacts(accounts, med_store),
            AppointmentFacts(accounts, appointments, clock=clock),
        ],
    )
    agent = CareAgent(gemini, memory, context)
    messenger = LineApiMessenger(settings.line_channel_access_token)

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
        messenger.push_text(line_user_id, agent.proactive(line_user_id, GREETING_INTENT))

    def care_one(line_user_id: str) -> None:
        messenger.push_text(line_user_id, agent.proactive(line_user_id, INACTIVITY_INTENT))

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
