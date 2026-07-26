"""獨立 RAG 週更 Worker：`python -m kinsun.rag.worker`。"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import load_dotenv, load_rag_worker_settings
from kinsun.cron.registry import rag_refresh_spec
from kinsun.cron.scheduler import Job, Scheduler
from kinsun.cron.state import PgScheduleStateStore
from kinsun.db import Database, ensure_schema
from kinsun.rag.refresh import refresh_known_urls
from kinsun.rag.schemas import ContentPolicy


def main() -> int:
    load_dotenv()
    args = _parse_args()
    settings = load_rag_worker_settings(os.environ)
    ensure_schema(settings.database_url)
    db = Database.open(
        settings.database_url,
        max_size=settings.database_pool_max_size,
    )
    timezone = ZoneInfo(settings.timezone)

    def run_refresh() -> None:
        version = refresh_known_urls(
            db,
            api_key=settings.gemini_api_key,
            embedding_model_name=settings.rag_embedding_model,
            content_policy=ContentPolicy(settings.rag_content_policy),
            audit_retention_days=settings.rag_audit_retention_days,
            crawler_delay_seconds=_env_float("RAG_CRAWLER_DELAY_SECONDS", 2.0),
            embedding_delay_seconds=_env_float("RAG_EMBEDDING_DELAY_SECONDS", 6.0),
            embedding_retries=_env_int("RAG_EMBEDDING_RETRIES", 5),
            embedding_retry_initial_delay_seconds=_env_float(
                "RAG_EMBEDDING_RETRY_INITIAL_DELAY_SECONDS", 30.0
            ),
            embedding_retry_max_delay_seconds=_env_float(
                "RAG_EMBEDDING_RETRY_MAX_DELAY_SECONDS", 300.0
            ),
            embedding_timeout_seconds=_env_float("RAG_EMBEDDING_TIMEOUT_SECONDS", 60.0),
            embedding_batch_size=_env_int("RAG_EMBEDDING_BATCH_SIZE", 20),
        )
        print(f"RAG 週更已發布：{version}")

    try:
        if args.once:
            run_refresh()
            return 0
        jobs = []
        if settings.rag_refresh_enabled:
            # 名稱與 cron 一律由 cron/registry.py 給（2026-07-27）：後台
            # `GET /admin/jobs` 以 job 名去 scheduler_state 查上次執行時間，名稱只要
            # 對不上，這支就會被那一頁誤報成「從未執行」——而它其實跑得好好的。
            spec = rag_refresh_spec(cron=settings.rag_refresh_cron)
            jobs.append(Job(spec.name, spec.cron, run_refresh))
        scheduler = Scheduler(
            jobs,
            lambda: datetime.now(timezone),
            PgScheduleStateStore(db, timezone),
        )
        print(
            "RAG Worker 啟動："
            + (
                f"排程 {settings.rag_refresh_cron}。"
                if settings.rag_refresh_enabled
                else "RAG_REFRESH_ENABLED=false，僅維持程序待命。"
            )
        )
        while True:
            scheduler.run_due()
            time.sleep(settings.scheduler_tick_seconds)
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KinSun 獨立 RAG 週更 Worker")
    parser.add_argument("--once", action="store_true", help="立即執行一次後結束")
    return parser.parse_args()


def _env_float(key: str, default: float) -> float:
    value = float(os.environ.get(key, str(default)))
    if value < 0:
        raise ValueError(f"{key} 不可小於 0。")
    return value


def _env_int(key: str, default: int) -> int:
    value = int(os.environ.get(key, str(default)))
    if value < 0:
        raise ValueError(f"{key} 不可小於 0。")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
