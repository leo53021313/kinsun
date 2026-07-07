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
    reminder_logs = core.reminder_logs
    agent = core.agent
    channel = core.channel
    traces = core.traces
    summaries = PgConversationSummaryStore(db, clock=clock)

    def run_one(elder_id: str) -> None:
        run_consolidation(elder_id, short_term=memory, long_term=long_term)
        try:
            summarize_day(
                elder_id,
                short_term=memory,
                summarizer=gemini,
                summaries=summaries,
                clock=clock,
            )
        except Exception:  # noqa: BLE001 - 摘要失敗不影響整理與其他長輩
            logger.warning("對話摘要失敗 elder=%s", elder_id)

    def _push_to_elder(elder_id: str, intent: str, kind: str) -> None:
        # 會話以 elder_id 識別；出站仍走 LINE，須反查綁定，未綁 LINE 即略過。
        elder = accounts.get_elder(elder_id)
        if elder is None or not elder.line_user_id:
            logger.warning("主動推播略過（長輩未綁 LINE）elder=%s kind=%s", elder_id, kind)
            return
        content = agent.proactive(elder_id, intent)
        channel.send_text(elder.line_user_id, content)
        # 主動推播補記 reminder_logs（觀測用，失敗不影響推播）。
        safe_record(reminder_logs.record, elder_id, kind, content)

    def greet_one(elder_id: str) -> None:
        _push_to_elder(elder_id, GREETING_INTENT, "proactive-greeting")

    def care_one(elder_id: str) -> None:
        _push_to_elder(elder_id, INACTIVITY_INTENT, "proactive-care")

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
                channel=channel,
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
            channel=channel,
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
