"""策略記憶持久層：守則的寫入、查詢、取代與撤銷。

`record` 為 append-only（新守則永遠是新一筆），寫入時 status 直接為 adopted——
守則自動生效，無人審佇列。帶 supersedes 時，新守則生效與舊守則退場必須在同一
交易內完成，否則 15 條上限會被突破（新的進來了、舊的還沒退）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.strategies.models import (
    STRATEGY_STATUS_ADOPTED,
    STRATEGY_STATUS_REVOKED,
    STRATEGY_STATUS_SUPERSEDED,
    Strategy,
)

_COLUMNS = (
    "strategy_id, elder_id, content, category, evidence, observed_days, "
    "status, supersedes_strategy_id, created_at, revoked_at"
)


class StrategyError(Exception):
    """策略記憶讀寫失敗。"""


class StrategyStore(Protocol):
    def record(
        self,
        elder_id: str,
        content: str,
        category: str,
        evidence: str,
        observed_days: int,
        supersedes_strategy_id: str | None,
    ) -> None: ...
    def list_for_elder(self, elder_id: str, *, status: str | None = None) -> list[Strategy]: ...
    def list_for_status(self, status: str) -> list[Strategy]: ...
    def revoke(self, strategy_id: str) -> None: ...


class PgStrategyStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = db
        self._errors = _Errors(db, lambda m: StrategyError(f"策略記憶存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(
        self,
        elder_id: str,
        content: str,
        category: str,
        evidence: str,
        observed_days: int,
        supersedes_strategy_id: str | None,
    ) -> None:
        now = self._clock().timestamp()
        try:
            with self._db.transaction() as tx:
                tx.execute(
                    "INSERT INTO strategies "
                    "(strategy_id, elder_id, content, category, evidence, observed_days, "
                    "status, supersedes_strategy_id, created_at, revoked_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                    (
                        self._new_id(),
                        elder_id,
                        content,
                        category,
                        evidence,
                        observed_days,
                        STRATEGY_STATUS_ADOPTED,
                        supersedes_strategy_id,
                        now,
                    ),
                )
                if supersedes_strategy_id:
                    tx.execute(
                        "UPDATE strategies SET status = %s WHERE strategy_id = %s "
                        "AND elder_id = %s AND status = %s",
                        (
                            STRATEGY_STATUS_SUPERSEDED,
                            supersedes_strategy_id,
                            elder_id,
                            STRATEGY_STATUS_ADOPTED,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001 - 一律翻成領域錯誤
            raise StrategyError(f"策略記憶存取失敗：{exc}") from exc

    def list_for_elder(self, elder_id: str, *, status: str | None = None) -> list[Strategy]:
        if status is None:
            rows = self._errors.query(
                f"SELECT {_COLUMNS} FROM strategies WHERE elder_id = %s ORDER BY created_at DESC",
                (elder_id,),
            )
        else:
            rows = self._errors.query(
                f"SELECT {_COLUMNS} FROM strategies WHERE elder_id = %s AND status = %s "
                "ORDER BY created_at DESC",
                (elder_id, status),
            )
        return [Strategy(*r) for r in rows]

    def list_for_status(self, status: str) -> list[Strategy]:
        rows = self._errors.query(
            f"SELECT {_COLUMNS} FROM strategies WHERE status = %s ORDER BY created_at DESC",
            (status,),
        )
        return [Strategy(*r) for r in rows]

    def revoke(self, strategy_id: str) -> None:
        self._errors.execute(
            "UPDATE strategies SET status = %s, revoked_at = %s "
            "WHERE strategy_id = %s AND status = %s",
            (
                STRATEGY_STATUS_REVOKED,
                self._clock().timestamp(),
                strategy_id,
                STRATEGY_STATUS_ADOPTED,
            ),
        )


class FakeStrategyStore:
    """StrategyStore 的記憶體替身（測試用，不碰 DB）。

    忠實複製 Pg 的行為：record 寫入即 adopted、帶 supersedes 時原子性退場舊守則、
    revoke 只對 adopted 生效。strategy_id 與 created_at 由索引虛構、僅供排序，
    故合約不斷言其值。回傳依 created_at 由新到舊排序，對齊 Pg 的 ORDER BY DESC。
    """

    def __init__(self) -> None:
        self._rows: list[Strategy] = []

    def record(
        self,
        elder_id: str,
        content: str,
        category: str,
        evidence: str,
        observed_days: int,
        supersedes_strategy_id: str | None,
    ) -> None:
        seq = float(len(self._rows))
        self._rows.append(
            Strategy(
                strategy_id=f"s{len(self._rows)}",
                elder_id=elder_id,
                content=content,
                category=category,
                evidence=evidence,
                observed_days=observed_days,
                status=STRATEGY_STATUS_ADOPTED,
                supersedes_strategy_id=supersedes_strategy_id,
                created_at=seq,
                revoked_at=None,
            )
        )
        if supersedes_strategy_id:
            self._replace(
                supersedes_strategy_id,
                STRATEGY_STATUS_SUPERSEDED,
                revoked_at=None,
                elder_id=elder_id,
            )

    def list_for_elder(self, elder_id: str, *, status: str | None = None) -> list[Strategy]:
        rows = [
            r
            for r in self._rows
            if r.elder_id == elder_id and (status is None or r.status == status)
        ]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def list_for_status(self, status: str) -> list[Strategy]:
        rows = [r for r in self._rows if r.status == status]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def revoke(self, strategy_id: str) -> None:
        self._replace(strategy_id, STRATEGY_STATUS_REVOKED, revoked_at=0.0, elder_id=None)

    def _replace(
        self, strategy_id: str, status: str, *, revoked_at: float | None, elder_id: str | None
    ) -> None:
        from dataclasses import replace

        for i, row in enumerate(self._rows):
            matches_elder = elder_id is None or row.elder_id == elder_id
            if (
                row.strategy_id == strategy_id
                and matches_elder
                and row.status == STRATEGY_STATUS_ADOPTED
            ):
                self._rows[i] = replace(row, status=status, revoked_at=revoked_at)
