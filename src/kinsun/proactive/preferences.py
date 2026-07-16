"""每位長輩的問候時間偏好：由夜間批次依她的活躍資料算出，問候 job 讀取。

單一狀態表（一位長輩一列），故 `save` 為 upsert 而非 append-only 事件流水帳
（D-42 例外：依語意命名檔案，三件套結構不變）。

sample_days 與 median_minute_of_day 是**可解釋性欄位**：要能看懂系統為什麼
決定九點半，而不是面對一個沒有來由的數字。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kinsun.db import Database, _Errors

_COLUMNS = "elder_id, hour, minute, computed_at, sample_days, median_minute_of_day"


@dataclass(frozen=True)
class GreetingPreference:
    elder_id: str
    hour: int
    minute: int  # 對齊半小時：0 或 30
    computed_at: float
    sample_days: int  # 憑幾天的資料算的（可解釋性）
    median_minute_of_day: int  # 她的中位活躍時刻，當天第幾分鐘（可解釋性）


class GreetingPreferenceError(Exception):
    """問候偏好讀寫失敗。"""


class GreetingPreferenceStore(Protocol):
    def save(self, pref: GreetingPreference) -> None: ...
    def get_for_elder(self, elder_id: str) -> GreetingPreference | None: ...
    def list_all(self) -> list[GreetingPreference]: ...


class PgGreetingPreferenceStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: GreetingPreferenceError(f"問候偏好存取失敗：{m}"))

    def save(self, pref: GreetingPreference) -> None:
        self._db.execute(
            f"INSERT INTO greeting_preferences ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (elder_id) DO UPDATE SET hour = EXCLUDED.hour, "
            "minute = EXCLUDED.minute, computed_at = EXCLUDED.computed_at, "
            "sample_days = EXCLUDED.sample_days, "
            "median_minute_of_day = EXCLUDED.median_minute_of_day",
            (
                pref.elder_id,
                pref.hour,
                pref.minute,
                pref.computed_at,
                pref.sample_days,
                pref.median_minute_of_day,
            ),
        )

    def get_for_elder(self, elder_id: str) -> GreetingPreference | None:
        row = self._db.query_one(
            f"SELECT {_COLUMNS} FROM greeting_preferences WHERE elder_id = %s", (elder_id,)
        )
        return GreetingPreference(*row) if row else None

    def list_all(self) -> list[GreetingPreference]:
        rows = self._db.query(f"SELECT {_COLUMNS} FROM greeting_preferences ORDER BY elder_id")
        return [GreetingPreference(*r) for r in rows]


class FakeGreetingPreferenceStore:
    """GreetingPreferenceStore 的記憶體替身（測試用，不碰 DB）。

    以 elder_id 為鍵做 upsert；list_all 依 elder_id 排序，對齊 Pg 的 ORDER BY。
    """

    def __init__(self) -> None:
        self._rows: dict[str, GreetingPreference] = {}

    def save(self, pref: GreetingPreference) -> None:
        self._rows[pref.elder_id] = pref

    def get_for_elder(self, elder_id: str) -> GreetingPreference | None:
        return self._rows.get(elder_id)

    def list_all(self) -> list[GreetingPreference]:
        return [self._rows[k] for k in sorted(self._rows)]
