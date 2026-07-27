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
    # 實際走的通道（✅ 庚-16，逗號串接如 "line,app"；空＝無可達通道或舊資料）。
    # App 通道＝落庫待拉取、非真送達——admin 據此區分顯示語意。
    channels: str = ""
    # 為什麼沒送到（2026-07-27）：`delivered` 只答「有沒有收到」，答不出「為什麼」，
    # 而這兩種「沒收到」的處置完全不同——`no_route`＝家屬還沒綁通道（要請他去綁，
    # 是常態、不是故障），`failed`＝出站真的丟例外（要維運介入）。先前兩者同樣記成
    # delivered=False，admin 的失敗告警於是被前者的常態雜訊淹掉。
    # 空字串＝本欄上線前的舊資料（未分類），失敗告警保守地照舊計入。
    outcome: str = ""


class RiskNotificationLogError(Exception):
    """送達紀錄讀寫失敗。"""


class RiskNotificationLogStore(Protocol):
    def record(
        self,
        elder_id: str,
        guardian_id: str,
        tier: RiskTier,
        *,
        delivered: bool,
        channels: str = "",
        outcome: str = "",
    ) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]: ...
    def count_failed_since(self, cutoff: float) -> int: ...


class PgRiskNotificationLogStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: RiskNotificationLogError(f"送達紀錄存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def record(
        self,
        elder_id: str,
        guardian_id: str,
        tier: RiskTier,
        *,
        delivered: bool,
        channels: str = "",
        outcome: str = "",
    ) -> None:
        self._db.execute(
            "INSERT INTO risk_notification_logs "
            "(risk_notification_log_id, elder_id, guardian_id, tier, delivered, "
            "created_at, channels, outcome) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                self._new_id(),
                elder_id,
                guardian_id,
                int(tier),
                delivered,
                self._clock().timestamp(),
                channels,
                outcome,
            ),
        )

    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]:
        rows = self._db.query(
            "SELECT risk_notification_log_id, elder_id, guardian_id, tier, delivered, "
            "created_at, channels, outcome FROM risk_notification_logs "
            "WHERE elder_id = %s ORDER BY created_at DESC",
            (elder_id,),
        )
        return [
            RiskNotificationLog(r[0], r[1], r[2], tier_from_db(r[3]), bool(r[4]), r[5], r[6], r[7])
            for r in rows
        ]

    def count_failed_since(self, cutoff: float) -> int:
        """近期**真的送失敗**的筆數，跨長輩全域——供 admin 告警門檻（✅ 庚-02）。

        `outcome = 'no_route'`（家屬還沒綁通道）刻意排除：那是常態、不是投遞故障，
        算進來會讓告警長期亮著、把真正的失敗淹掉（2026-07-27）。舊資料的 outcome
        為空字串，保守地照舊計入——寧可多報，不可讓歷史失敗憑空消失。
        """
        row = self._db.query_one(
            "SELECT count(*) FROM risk_notification_logs "
            "WHERE delivered = FALSE AND outcome <> 'no_route' AND created_at >= %s",
            (cutoff,),
        )
        return int(row[0]) if row else 0


class FakeRiskNotificationLogStore:
    """RiskNotificationLogStore 的記憶體替身（測試用，不碰 DB）。

    與 Pg 合約對齊：list_for_elder 以「最近先」順序回傳；id 與 created_at 為
    合成值（記錄序號），合約不應對其斷言。若需以 created_at 過濾（如 count_failed_since），
    注入 clock（回傳 epoch 秒）使時間戳與 Pg 對齊。
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self.recorded: list[RiskNotificationLog] = []
        self._clock = clock

    def record(
        self,
        elder_id: str,
        guardian_id: str,
        tier: RiskTier,
        *,
        delivered: bool,
        channels: str = "",
        outcome: str = "",
    ) -> None:
        index = len(self.recorded)
        created_at = self._clock() if self._clock else float(index)
        self.recorded.append(
            RiskNotificationLog(
                str(index), elder_id, guardian_id, tier, delivered, created_at, channels, outcome
            )
        )

    def list_for_elder(self, elder_id: str) -> list[RiskNotificationLog]:
        return [d for d in reversed(self.recorded) if d.elder_id == elder_id]

    def count_failed_since(self, cutoff: float) -> int:
        return sum(
            1
            for d in self.recorded
            if not d.delivered and d.outcome != "no_route" and d.created_at >= cutoff
        )
