"""提醒紀錄持久化：供日後健康報告查詢。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors

logger = logging.getLogger("kinsun.reports.reminders")


@dataclass(frozen=True)
class ReminderLog:
    reminder_log_id: str
    elder_id: str
    kind: str
    content: str
    created_at: float


class ReminderLogError(Exception):
    """提醒紀錄讀寫失敗。"""


class ReminderLogStore(Protocol):
    def record(self, elder_id: str, kind: str, content: str) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[ReminderLog]: ...


class PgReminderLogStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: ReminderLogError(f"提醒紀錄存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, elder_id: str, kind: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO reminder_logs (reminder_log_id, elder_id, kind, content, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (self._new_id(), elder_id, kind, content, self._clock().timestamp()),
        )

    def list_for_elder(self, elder_id: str) -> list[ReminderLog]:
        rows = self._db.query(
            "SELECT reminder_log_id, elder_id, kind, content, created_at FROM reminder_logs "
            "WHERE elder_id = %s ORDER BY created_at DESC",
            (elder_id,),
        )
        return [ReminderLog(*r) for r in rows]


def safe_record(
    record: Callable[[str, str, str], None] | None, elder_id: str, kind: str, content: str
) -> None:
    if record is None:
        return
    try:
        record(elder_id, kind, content)
    except Exception:  # noqa: BLE001 - 記錄失敗不影響推播
        logger.warning("提醒紀錄落庫失敗 elder=%s kind=%s", elder_id, kind)
