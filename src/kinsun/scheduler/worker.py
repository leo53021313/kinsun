"""排程 worker：長跑迴圈，定時 run_due。

CLI：PYTHONPATH=src uv run python -m kinsun.scheduler
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kinsun.accounts.repository import PgAccountRepository
from kinsun.accounts.service import AccountService
from kinsun.agent import CareAgent
from kinsun.appointment.facts import AppointmentFacts
from kinsun.appointment.jobs import build_appointment_reminder_job
from kinsun.appointment.service import AppointmentService
from kinsun.appointment.store import PgAppointmentStore
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.config import Settings, load_settings
from kinsun.db import Database, ensure_schema
from kinsun.llm import GeminiClient
from kinsun.longterm.consolidation import run_consolidation
from kinsun.longterm.store import Mem0LongTermStore
from kinsun.medication.facts import MedicationFacts
from kinsun.medication.jobs import build_medication_slot_job
from kinsun.medication.models import MedicationSlot
from kinsun.medication.store import PgMedicationStore
from kinsun.mem0_factory import build_mem0_memory
from kinsun.memory.store import PgMemoryStore
from kinsun.proactive.jobs import (
    GREETING_INTENT,
    INACTIVITY_INTENT,
    build_greeting_job,
    build_inactivity_job,
)
from kinsun.recall import MemoryContext
from kinsun.reports.reminders import PgReminderLogStore
from kinsun.scheduler.jobs import build_consolidation_job
from kinsun.scheduler.scheduler import Scheduler
from kinsun.scheduler.state import PgScheduleStateStore


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
        timeout=settings.llm_timeout_seconds,
    )
    long_term = Mem0LongTermStore(build_mem0_memory(settings), top_k=settings.longterm_top_k)
    accounts = AccountService(PgAccountRepository(db), clock=clock)
    med_store = PgMedicationStore(db)
    appt_store = PgAppointmentStore(db)
    appointments = AppointmentService(appt_store)
    reminder_logs = PgReminderLogStore(db, clock=clock, new_id=lambda: uuid.uuid4().hex)
    context = MemoryContext(
        long_term,
        facts=[
            MedicationFacts(accounts, med_store),
            AppointmentFacts(accounts, appointments, clock=clock),
        ],
    )
    agent = CareAgent(gemini, memory, context)
    messenger = LineApiMessenger(settings.line_channel_access_token)

    def run_one(session_id: str) -> None:
        run_consolidation(session_id, short_term=memory, long_term=long_term)

    def greet_one(session_id: str) -> None:
        messenger.push_text(session_id, agent.proactive(session_id, GREETING_INTENT))

    def care_one(session_id: str) -> None:
        messenger.push_text(session_id, agent.proactive(session_id, INACTIVITY_INTENT))

    jobs = [
        build_consolidation_job(
            sessions=memory.sessions, run_one=run_one, hour=settings.consolidation_hour
        ),
        build_greeting_job(
            sessions=memory.sessions, greet_one=greet_one, hour=settings.greeting_hour
        ),
        build_inactivity_job(
            sessions=memory.sessions,
            last_active=memory.last_active,
            clock=clock,
            threshold_seconds=settings.inactivity_days * 86400,
            care_one=care_one,
            hour=settings.inactivity_hour,
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
                is_consented=accounts.is_consented_elder,
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
            is_consented=accounts.is_consented_elder,
            guardian_line_ids=accounts.guardian_line_ids_of_elder,
            push=messenger.push_text,
            hour=settings.appointment_reminder_hour,
            record=reminder_logs.record,
        )
    )
    state = PgScheduleStateStore(db, tz)
    return Scheduler(jobs, clock, state), db


def serve(scheduler: Scheduler, *, tick_seconds: int) -> None:
    while True:
        scheduler.run_due()
        time.sleep(tick_seconds)


def main() -> int:
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    scheduler, db = build_scheduler(settings, clock=lambda: datetime.now(tz))
    print(
        f"排程器啟動：每 {settings.scheduler_tick_seconds}s 檢查；"
        f"整理 {settings.consolidation_hour}:00、問候 {settings.greeting_hour}:00、"
        f"失聯關心 {settings.inactivity_hour}:00（{settings.inactivity_days} 天門檻）。"
    )
    try:
        serve(scheduler, tick_seconds=settings.scheduler_tick_seconds)
    finally:
        db.close()
    return 0
