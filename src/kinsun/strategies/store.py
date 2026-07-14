"""策略記憶持久層：守則的寫入、查詢、取代與撤銷。

`record` 為 append-only（新守則永遠是新一筆），寫入時 status 直接為 adopted——
守則自動生效，無人審佇列。帶 supersedes 時，新守則生效與舊守則退場必須在同一
交易內完成，否則 15 條上限會被突破（新的進來了、舊的還沒退）。

取代對象必須「存在、屬於同一位長輩、且仍在 adopted」，否則整筆拒收（見
`_require_adopted`）。這道守門是上限不變量的地基：少了它，反思拿一個已被人工
撤銷的 strategy_id 來 supersede，就會變成新守則照樣生效、沒有任何舊守則退場，
adopted 淨增一條——被撤銷的守則等於用另一條近似守則復活，正是撤銷要阻止的事。

category 白名單在此處再驗一次（縱深防禦）：唯一寫入路徑雖然已有反思端的內容
濾網，但後台手動新增、資料修補腳本等旁路寫入端不會經過它，而注入端只認
status='adopted'。注意白名單只擋分類、擋不住危險內容——真正的內容過濾在反思端。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, Executor, _Errors
from kinsun.strategies.models import (
    STRATEGY_CATEGORIES,
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
    """策略記憶讀寫失敗，或寫入違反守則不變量（分類白名單、取代對象合法性）。"""


def _validate_category(category: str) -> None:
    if category not in STRATEGY_CATEGORIES:
        raise StrategyError(f"守則分類不在白名單：{category}")


def _reject_supersedes(strategy_id: str) -> StrategyError:
    return StrategyError(f"欲取代的守則不存在、不屬於此長輩，或已不在生效中：{strategy_id}")


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
        self._db = _Errors(db, lambda m: StrategyError(f"策略記憶存取失敗：{m}"))
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
        """寫入一條生效中的守則；帶 supersedes 時同交易內讓舊守則退場。

        取代對象不合法（不存在／別位長輩／已 revoked 或 superseded）時丟 StrategyError，
        整筆不寫入。
        """
        _validate_category(category)
        now = self._clock().timestamp()
        with self._db.transaction() as tx:
            # 先鎖後寫：守門通過才 INSERT，兩個寫入者同時 supersede 同一條時，後到者
            # 會卡在 FOR UPDATE，待前者 commit 後讀到 superseded 而被擋下。守門丟出的
            # StrategyError 是業務例外，會原樣穿透 Database.transaction()（只翻譯
            # psycopg 錯誤）並照常回滾。
            if supersedes_strategy_id:
                self._require_adopted(tx, elder_id, supersedes_strategy_id)
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

    def _require_adopted(self, tx: Executor, elder_id: str, strategy_id: str) -> None:
        row = tx.query_one(
            "SELECT status FROM strategies WHERE strategy_id = %s AND elder_id = %s FOR UPDATE",
            (strategy_id, elder_id),
        )
        if row is None or row[0] != STRATEGY_STATUS_ADOPTED:
            raise _reject_supersedes(strategy_id)

    def list_for_elder(self, elder_id: str, *, status: str | None = None) -> list[Strategy]:
        if status is None:
            rows = self._db.query(
                f"SELECT {_COLUMNS} FROM strategies WHERE elder_id = %s ORDER BY created_at DESC",
                (elder_id,),
            )
        else:
            rows = self._db.query(
                f"SELECT {_COLUMNS} FROM strategies WHERE elder_id = %s AND status = %s "
                "ORDER BY created_at DESC",
                (elder_id, status),
            )
        return [Strategy(*r) for r in rows]

    def list_for_status(self, status: str) -> list[Strategy]:
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM strategies WHERE status = %s ORDER BY created_at DESC",
            (status,),
        )
        return [Strategy(*r) for r in rows]

    def revoke(self, strategy_id: str) -> None:
        self._db.execute(
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

    忠實複製 Pg 的行為：record 寫入即 adopted、分類與取代對象不合法時丟 StrategyError、
    帶 supersedes 時原子性退場舊守則、revoke 只對 adopted 生效（撤銷不存在的 id 是靜默
    no-op，同 Pg 的 0 列 UPDATE）。strategy_id 與 created_at 由索引虛構、僅供排序，故
    合約不斷言其值；revoked_at 則取自可注入的 clock（epoch 秒），與 Pg 對齊。回傳依
    created_at 由新到舊排序，對齊 Pg 的 ORDER BY DESC。
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._rows: list[Strategy] = []
        self._clock = clock

    def record(
        self,
        elder_id: str,
        content: str,
        category: str,
        evidence: str,
        observed_days: int,
        supersedes_strategy_id: str | None,
    ) -> None:
        _validate_category(category)
        if supersedes_strategy_id:
            self._require_adopted(elder_id, supersedes_strategy_id)
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
        # 未注入 clock 時沿用合成時間戳，與既有測試相容（比照 FakeRiskEventStore）。
        now = self._clock() if self._clock else 0.0
        self._replace(strategy_id, STRATEGY_STATUS_REVOKED, revoked_at=now, elder_id=None)

    def _require_adopted(self, elder_id: str, strategy_id: str) -> None:
        row = next(
            (r for r in self._rows if r.strategy_id == strategy_id and r.elder_id == elder_id),
            None,
        )
        if row is None or row.status != STRATEGY_STATUS_ADOPTED:
            raise _reject_supersedes(strategy_id)

    def _replace(
        self, strategy_id: str, status: str, *, revoked_at: float | None, elder_id: str | None
    ) -> None:
        for i, row in enumerate(self._rows):
            matches_elder = elder_id is None or row.elder_id == elder_id
            if (
                row.strategy_id == strategy_id
                and matches_elder
                and row.status == STRATEGY_STATUS_ADOPTED
            ):
                self._rows[i] = replace(row, status=status, revoked_at=revoked_at)
