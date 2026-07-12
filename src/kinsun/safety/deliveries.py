"""危急通知送達紀錄（✅ D-36，丙-7）：每位家屬成功／失敗獨立留痕。

append-only 事件流水帳（D-42 例外：依語意命名檔案），回答「家屬當時
有沒有收到」——通知本體失敗只記錄不中斷，留痕失敗同樣不得反噬通知。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.safety.tiers import RiskTier, tier_from_db


@dataclass(frozen=True)
class RiskNotificationLog:
    risk_notification_log_id: str
    elder_id: str
    guardian_id: str
    tier: RiskTier
    delivered: bool
    created_at: float


class RiskNotificationLogError(Exception):
    """送達紀錄讀寫失敗。"""


class RiskNotificationLogStore(Protocol):
    def record(
        self, elder_id: str, guardian_id: str, tier: RiskTier, *, delivered: bool
    ) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]: ...


class PgRiskNotificationLogStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: RiskNotificationLogError(f"送達紀錄存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, elder_id: str, guardian_id: str, tier: RiskTier, *, delivered: bool) -> None:
        self._db.execute(
            "INSERT INTO risk_notification_logs "
            "(risk_notification_log_id, elder_id, guardian_id, tier, delivered, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                elder_id,
                guardian_id,
                int(tier),
                delivered,
                self._clock().timestamp(),
            ),
        )

    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]:
        rows = self._db.query(
            "SELECT risk_notification_log_id, elder_id, guardian_id, tier, delivered, created_at "
            "FROM risk_notification_logs WHERE elder_id = %s ORDER BY created_at DESC",
            (elder_id,),
        )
        return [
            RiskNotificationLog(r[0], r[1], r[2], tier_from_db(r[3]), bool(r[4]), r[5])
            for r in rows
        ]


class FakeRiskNotificationLogStore:
    """RiskNotificationLogStore 的記憶體替身（測試用，不碰 DB）。

    與 Pg 合約對齊：list_for_elder 以「最近先」順序回傳；id 與 created_at 為
    合成值（記錄序號），合約不應對其斷言。
    """

    def __init__(self) -> None:
        self.recorded: list[RiskNotificationLog] = []

    def record(self, elder_id: str, guardian_id: str, tier: RiskTier, *, delivered: bool) -> None:
        index = len(self.recorded)
        self.recorded.append(
            RiskNotificationLog(str(index), elder_id, guardian_id, tier, delivered, float(index))
        )

    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]:
        return [d for d in reversed(self.recorded) if d.elder_id == elder_id]
