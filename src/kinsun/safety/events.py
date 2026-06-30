"""危急事件持久化：供日後健康報告查詢。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.safety.tiers import RiskAssessment, RiskTier


@dataclass(frozen=True)
class RiskEvent:
    event_id: str
    session_id: str
    tier: RiskTier
    reason: str
    created_at: float


class RiskEventError(Exception):
    """危急事件讀寫失敗。"""


class RiskEventStore(Protocol):
    def record(self, session_id: str, assessment: RiskAssessment) -> None: ...
    def list_for_session(self, session_id: str) -> list[RiskEvent]: ...


class PgRiskEventStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: RiskEventError(f"危急事件存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, session_id: str, assessment: RiskAssessment) -> None:
        self._db.execute(
            "INSERT INTO risk_events (event_id, session_id, tier, reason, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                self._new_id(),
                session_id,
                int(assessment.tier),
                assessment.reason,
                self._clock().timestamp(),
            ),
        )

    def list_for_session(self, session_id: str) -> list[RiskEvent]:
        rows = self._db.query(
            "SELECT event_id, session_id, tier, reason, created_at FROM risk_events "
            "WHERE session_id = %s ORDER BY created_at DESC",
            (session_id,),
        )
        return [RiskEvent(r[0], r[1], RiskTier(r[2]), r[3], r[4]) for r in rows]
