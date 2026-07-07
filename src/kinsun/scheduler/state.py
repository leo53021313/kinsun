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


class FakeScheduleStateStore:
    """ScheduleStateStore 的記憶體替身（測試用，不碰 DB）。

    與 PgScheduleStateStore 的差異：Pg 以 epoch 秒（DOUBLE PRECISION）存讀，
    get_last_run 會用建構時的 tz 重建 datetime；本替身則原樣保存傳入的 datetime。
    對「時間點」（`.timestamp()`／aware datetime 的 `==`）兩者一致，故合約測試以
    `.timestamp()` 比較。無 tz 參數的替身無法在此處複製 Pg 的 tz 正規化，也不需要。
    """

    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def get_last_run(self, job_name: str) -> datetime | None:
        return self._last.get(job_name)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._last[job_name] = when
