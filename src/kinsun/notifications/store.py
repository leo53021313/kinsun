"""App 內通知持久化（✅ D-12，甲-6）：App 出站 adapter 寫入、App 端登入後拉取。

真推播（D-08 階段 5）到位前，這是純 App 使用者接收危急通知／提醒／主動關懷的
唯一路徑。鍵為通道帳號識別 external_id（channel_bindings 的 App 通道欄位），
讀取端以本人的全部 App 綁定聚合查詢。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kinsun.db import Database, _Errors


@dataclass(frozen=True)
class AppNotification:
    app_notification_id: str
    external_id: str
    content: str
    created_at: float


class AppNotificationError(Exception):
    """App 內通知讀寫失敗。"""


class AppNotificationStore(Protocol):
    def record(self, external_id: str, content: str) -> None: ...
    def list_for_external_ids(
        self, external_ids: list[str], *, limit: int = 50
    ) -> list[AppNotification]: ...


class PgAppNotificationStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: AppNotificationError(f"App 通知存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(self, external_id: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO app_notifications "
            "(app_notification_id, external_id, content, created_at) VALUES (%s, %s, %s, %s)",
            (self._new_id(), external_id, content, self._clock().timestamp()),
        )

    def list_for_external_ids(
        self, external_ids: list[str], *, limit: int = 50
    ) -> list[AppNotification]:
        if not external_ids:
            return []
        rows = self._db.query(
            "SELECT app_notification_id, external_id, content, created_at "
            "FROM app_notifications WHERE external_id = ANY(%s) "
            "ORDER BY created_at DESC LIMIT %s",
            (external_ids, limit),
        )
        return [AppNotification(*r) for r in rows]


class FakeAppNotificationStore:
    """AppNotificationStore 的記憶體替身（測試用，不碰 DB）。

    與 Pg 合約對齊：list 以「最近先」排序、支援多 external_id 聚合與 limit。
    app_notification_id 與 created_at 為合成值（記錄序號），合約不應對其斷言；
    可注入 clock 取得真實時間戳（合約測試用）。
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self.recorded: list[AppNotification] = []
        self._clock = clock

    def record(self, external_id: str, content: str) -> None:
        index = len(self.recorded)
        created_at = self._clock() if self._clock else float(index)
        self.recorded.append(AppNotification(str(index), external_id, content, created_at))

    def list_for_external_ids(
        self, external_ids: list[str], *, limit: int = 50
    ) -> list[AppNotification]:
        rows = [n for n in self.recorded if n.external_id in external_ids]
        rows.sort(key=lambda n: n.created_at, reverse=True)
        return rows[:limit]
