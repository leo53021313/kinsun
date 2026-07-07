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
    risk_event_id: str
    elder_id: str
    tier: RiskTier
    reason: str
    created_at: float


class RiskEventError(Exception):
    """危急事件讀寫失敗。"""


class RiskEventStore(Protocol):
    def record(
        self, elder_id: str, assessment: RiskAssessment, *, trace_id: str | None = None
    ) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[RiskEvent]: ...


class PgRiskEventStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: RiskEventError(f"危急事件存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(
        self, elder_id: str, assessment: RiskAssessment, *, trace_id: str | None = None
    ) -> None:
        self._db.execute(
            "INSERT INTO risk_events "
            "(risk_event_id, elder_id, tier, reason, created_at, trace_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                elder_id,
                int(assessment.tier),
                assessment.reason,
                self._clock().timestamp(),
                trace_id,
            ),
        )

    def list_for_elder(self, elder_id: str) -> list[RiskEvent]:
        rows = self._db.query(
            "SELECT risk_event_id, elder_id, tier, reason, created_at FROM risk_events "
            "WHERE elder_id = %s ORDER BY created_at DESC",
            (elder_id,),
        )
        return [RiskEvent(r[0], r[1], RiskTier(r[2]), r[3], r[4]) for r in rows]


class FakeRiskEventStore:
    """RiskEventStore 的記憶體替身（測試用，不碰 DB）。

    與 PgRiskEventStore 合約對齊：list_for_elder 以「最近先」順序回傳
    （對應 Pg 的 ORDER BY created_at DESC）。risk_event_id 與 created_at 為
    依記錄序號合成的值，不保證與 Pg 相同，合約不應對其斷言。trace_id 會保存於
    recorded_trace_ids 供內省；與 Pg 相同，不經由 RiskEvent／list_for_elder
    對外揭露。
    """

    def __init__(self) -> None:
        self.recorded: list[tuple[str, RiskAssessment]] = []
        self.recorded_trace_ids: list[str | None] = []

    def record(
        self, elder_id: str, assessment: RiskAssessment, *, trace_id: str | None = None
    ) -> None:
        self.recorded.append((elder_id, assessment))
        self.recorded_trace_ids.append(trace_id)

    def list_for_elder(self, elder_id: str) -> list[RiskEvent]:
        rows = [(i, s, a) for i, (s, a) in enumerate(self.recorded) if s == elder_id]
        return [RiskEvent(str(i), s, a.tier, a.reason, float(i)) for i, s, a in reversed(rows)]
