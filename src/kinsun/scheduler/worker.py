"""排程 worker：長跑迴圈，定時 run_due。

CLI：PYTHONPATH=src uv run python -m kinsun.scheduler
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import Settings, load_settings
from kinsun.episodic.embeddings import GeminiEmbedder
from kinsun.episodic.store import SqliteVectorStore
from kinsun.knowledge.store import SqliteFactStore
from kinsun.llm import GeminiClient
from kinsun.longterm.consolidation import run_consolidation
from kinsun.longterm.extractor import ConsolidationExtractor
from kinsun.memory.store import SqliteMemoryStore
from kinsun.scheduler.jobs import build_consolidation_job
from kinsun.scheduler.scheduler import Scheduler


def build_scheduler(settings: Settings, *, clock: Callable[[], datetime]) -> Scheduler:
    tz = ZoneInfo(settings.timezone)
    memory = SqliteMemoryStore(
        settings.memory_db_path,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    extractor = ConsolidationExtractor(
        GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.llm_timeout_seconds,
        )
    )
    embedder = GeminiEmbedder(api_key=settings.gemini_api_key, model=settings.embedding_model)
    fact_store = SqliteFactStore(settings.knowledge_db_path)
    vector_store = SqliteVectorStore(settings.episodic_db_path)

    def run_one(session_id: str) -> None:
        run_consolidation(
            session_id,
            short_term=memory,
            extractor=extractor,
            embedder=embedder,
            fact_store=fact_store,
            vector_store=vector_store,
        )

    job = build_consolidation_job(
        sessions=memory.sessions, run_one=run_one, hour=settings.consolidation_hour
    )
    return Scheduler([job], clock)


def serve(scheduler: Scheduler, *, tick_seconds: int) -> None:
    while True:
        scheduler.run_due()
        time.sleep(tick_seconds)


def main() -> int:
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    scheduler = build_scheduler(settings, clock=lambda: datetime.now(tz))
    print(
        f"排程器啟動：每 {settings.scheduler_tick_seconds}s 檢查，"
        f"每日 {settings.consolidation_hour}:00 整理。"
    )
    serve(scheduler, tick_seconds=settings.scheduler_tick_seconds)
    return 0
