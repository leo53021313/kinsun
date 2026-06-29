"""排程 worker：長跑迴圈，定時 run_due。

CLI：PYTHONPATH=src uv run python -m kinsun.scheduler
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.agent import CareAgent
from kinsun.channels.line.messenger import LineApiMessenger
from kinsun.config import Settings, load_settings
from kinsun.db import ensure_schema
from kinsun.llm import GeminiClient
from kinsun.longterm.consolidation import run_consolidation
from kinsun.longterm.store import Mem0LongTermStore
from kinsun.mem0_factory import build_mem0_memory
from kinsun.memory.store import PgMemoryStore
from kinsun.proactive.jobs import (
    GREETING_INTENT,
    INACTIVITY_INTENT,
    build_greeting_job,
    build_inactivity_job,
)
from kinsun.recall import MemoryContext
from kinsun.scheduler.jobs import build_consolidation_job
from kinsun.scheduler.scheduler import Scheduler
from kinsun.scheduler.state import PgScheduleStateStore


def build_scheduler(settings: Settings, *, clock: Callable[[], datetime]) -> Scheduler:
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
    agent = CareAgent(gemini, memory, MemoryContext(long_term))
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
    state = PgScheduleStateStore(settings.database_url, tz)
    return Scheduler(jobs, clock, state)


def serve(scheduler: Scheduler, *, tick_seconds: int) -> None:
    while True:
        scheduler.run_due()
        time.sleep(tick_seconds)


def main() -> int:
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    scheduler = build_scheduler(settings, clock=lambda: datetime.now(tz))
    print(
        f"排程器啟動：每 {settings.scheduler_tick_seconds}s 檢查；"
        f"整理 {settings.consolidation_hour}:00、問候 {settings.greeting_hour}:00、"
        f"失聯關心 {settings.inactivity_hour}:00（{settings.inactivity_days} 天門檻）。"
    )
    serve(scheduler, tick_seconds=settings.scheduler_tick_seconds)
    return 0
