"""排程狀態持久化：每個 job 的 last_run。Protocol + Postgres 實作。"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Protocol

from kinsun.db import connect


class ScheduleStateError(Exception):
    """排程狀態讀寫失敗。"""


class ScheduleStateStore(Protocol):
    def get_last_run(self, job_name: str) -> datetime | None: ...
    def set_last_run(self, job_name: str, when: datetime) -> None: ...


class PgScheduleStateStore:
    """排程狀態的 Postgres（Supabase）實作；介面同 ScheduleStateStore。"""

    def __init__(self, database_url: str, tz: tzinfo) -> None:
        self._url = database_url
        self._tz = tz

    def get_last_run(self, job_name: str) -> datetime | None:
        try:
            with connect(self._url) as conn:
                row = conn.execute(
                    "SELECT last_run_at FROM scheduler_state WHERE job_name = %s",
                    (job_name,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise ScheduleStateError(f"讀取排程狀態失敗：{exc}") from exc
        if row is None or row[0] is None:
            return None
        return datetime.fromtimestamp(row[0], self._tz)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        try:
            with connect(self._url) as conn:
                conn.execute(
                    "INSERT INTO scheduler_state (job_name, last_run_at) VALUES (%s, %s) "
                    "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at",
                    (job_name, when.timestamp()),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise ScheduleStateError(f"寫入排程狀態失敗：{exc}") from exc
