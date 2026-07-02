"""排程狀態持久化：每個 job 的 last_run。Protocol + Postgres 實作。"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Protocol

from kinsun.db import Database, _Errors


class ScheduleStateError(Exception):
    """排程狀態讀寫失敗。"""


class ScheduleStateStore(Protocol):
    def get_last_run(self, job_name: str) -> datetime | None: ...
    def set_last_run(self, job_name: str, when: datetime) -> None: ...


class PgScheduleStateStore:
    """排程狀態的 Postgres（Supabase）實作；介面同 ScheduleStateStore。"""

    def __init__(self, db: Database, tz: tzinfo) -> None:
        self._db = _Errors(db, lambda m: ScheduleStateError(f"排程狀態存取失敗：{m}"))
        self._tz = tz

    def get_last_run(self, job_name: str) -> datetime | None:
        row = self._db.query_one(
            "SELECT last_run_at FROM scheduler_state WHERE job_name = %s",
            (job_name,),
        )
        if row is None or row[0] is None:
            return None
        return datetime.fromtimestamp(row[0], self._tz)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._db.execute(
            "INSERT INTO scheduler_state (job_name, last_run_at) VALUES (%s, %s) "
            "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at",
            (job_name, when.timestamp()),
        )
