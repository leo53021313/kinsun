"""整理進度標記（✅ 庚-06／庚-13）：記「某長輩某日已整理進長期記憶」。

單一狀態表（D-42 例外：依語意命名檔案），主鍵 (elder_id, day)。兩個用途：
- 冪等（庚-13）：同日重跑（含 admin 手動觸發）跳過已整理日，不重覆 mem0.add。
- 補齊（庚-06）：worker 停機跨多日重啟時，據此得知從哪一天起要補整理。

三件套結構不變：`ConsolidationLogStore`（Protocol）＋`Pg…`＋`Fake…` 同住本檔。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors


class ConsolidationLogError(Exception):
    """整理標記讀寫失敗。"""


class ConsolidationLogStore(Protocol):
    def consolidated_days(self, elder_id: str) -> set[str]: ...
    def record(self, elder_id: str, day: str, *, turn_count: int) -> None: ...


class PgConsolidationLogStore:
    def __init__(self, db: Database, *, clock: Callable[[], datetime]) -> None:
        self._db = _Errors(db, lambda m: ConsolidationLogError(f"整理標記存取失敗：{m}"))
        self._clock = clock

    def consolidated_days(self, elder_id: str) -> set[str]:
        rows = self._db.query(
            "SELECT day FROM memory_consolidations WHERE elder_id = %s",
            (elder_id,),
        )
        return {r[0] for r in rows}

    def record(self, elder_id: str, day: str, *, turn_count: int) -> None:
        """標記某日已整理；重覆標記為 no-op（ON CONFLICT DO NOTHING）確保冪等。"""
        self._db.execute(
            "INSERT INTO memory_consolidations (elder_id, day, turn_count, created_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (elder_id, day) DO NOTHING",
            (elder_id, day, turn_count, self._clock().timestamp()),
        )


class FakeConsolidationLogStore:
    """ConsolidationLogStore 的記憶體替身（測試用，不碰 DB）。

    與 Pg 合約對齊：record 對已存在的 (elder_id, day) 為 no-op（冪等）。
    """

    def __init__(self) -> None:
        self.marked: dict[str, dict[str, int]] = {}

    def consolidated_days(self, elder_id: str) -> set[str]:
        return set(self.marked.get(elder_id, {}))

    def record(self, elder_id: str, day: str, *, turn_count: int) -> None:
        self.marked.setdefault(elder_id, {}).setdefault(day, turn_count)
