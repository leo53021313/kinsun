"""提醒紀錄持久化：供日後健康報告查詢。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from kinsun.db import Database, _Errors

logger = logging.getLogger("kinsun.reports.reminders")


# 提醒種類集中列舉（✅ 庚-40／A-36）：寫入端（medications／appointments jobs、
# proactive 推播）與讀取端（健康報告、admin）共用；新增種類先加這裡。
#
# ⚠️ 這張表的紀錄有**兩種角色**，寫入失敗的政策**完全相反**，不可統一（spec 2026-07-16）：
#
# * 純觀測（medication／appointment／proactive-care）：紀錄只供健康報告，冪等由各自
#   每天一次的 cron 保證。故**先推播、`sent == 0` 就不記**（庚-14：沒送到的提醒不該
#   出現在家屬的健康報告裡，保報告誠實）。寫入失敗用 safe_record 吞掉——拿一個報表
#   寫入去擋推播，等於報表壞了長輩就收不到關心。
# * 冪等帳本（proactive-greeting）：問候 job 每半小時掃描（cron `0,30 * * * *`），
#   「今天問候過沒」全靠 greeted_today 讀這張表。故**先記帳、記不了就不推**——若用
#   safe_record 吞掉寫入失敗，greeted_today 恆為 false，於是從她的偏好時間起每半小時
#   推一則早安到當天結束（約 30 則，每則還燒一次 LLM）。
#
# 同一張表無法同時滿足兩者（一個要「送到才記」，一個要「記了才送」）。衝突時
# **安全（不轟炸長輩）必須贏**，誠實退居其次——代價是送達 0 通道的問候仍會記帳、
# 出現在健康報告裡（庚-14 在問候類上的已知缺口，非本次引入；長期正解是補
# `reminder_logs.delivered` 欄位，比照 safety/notifier.py 的 risk_notification_logs，
# 讓帳本記「試過了」、報告濾「真送到的」。屬 DDL 變更，另案）。
#
# 回歸測試（改動前請先讀，兩條政策各有一條釘死）：
#   tests/test_scheduler_worker.py::test_a_greeting_it_cannot_book_is_never_sent
#   tests/test_scheduler_worker.py::test_a_care_message_still_goes_out_when_the_ledger_is_down
REMINDER_KIND_MEDICATION = "medication"
REMINDER_KIND_APPOINTMENT = "appointment"
REMINDER_KIND_PROACTIVE_GREETING = "proactive-greeting"
REMINDER_KIND_PROACTIVE_CARE = "proactive-care"
REMINDER_KINDS = (
    REMINDER_KIND_MEDICATION,
    REMINDER_KIND_APPOINTMENT,
    REMINDER_KIND_PROACTIVE_GREETING,
    REMINDER_KIND_PROACTIVE_CARE,
)


@dataclass(frozen=True)
class ReminderLog:
    reminder_log_id: str
    elder_id: str
    kind: str  # ∈ REMINDER_KINDS
    content: str
    created_at: float
    responded_at: float | None = None  # 長輩在時間窗內有發言即標記；None＝未回應


class ReminderLogError(Exception):
    """提醒紀錄讀寫失敗。"""


class ReminderLogStore(Protocol):
    def record(self, elder_id: str, kind: str, content: str) -> None: ...
    def list_for_elder(self, elder_id: str) -> list[ReminderLog]: ...
    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[ReminderLog]: ...

    def mark_responded(self, elder_id: str, *, now: float, within_seconds: int) -> None:
        """把時間窗內**最近一則**提醒標為已回應；該則若已標記過則不動作。

        「尚未標記」是更新條件、不是候選條件——見 PgReminderLogStore.mark_responded。
        同一 created_at 有多則提醒時，選中哪一則為**未定義行為**（Fake 與 Pg 不保證
        一致）：真實世界不會撞秒，呼叫端不應依賴此情形的結果。
        """
        ...


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
            "SELECT reminder_log_id, elder_id, kind, content, created_at, responded_at "
            "FROM reminder_logs WHERE elder_id = %s ORDER BY created_at DESC",
            (elder_id,),
        )
        return [ReminderLog(*r) for r in rows]

    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[ReminderLog]:
        rows = self._db.query(
            "SELECT reminder_log_id, elder_id, kind, content, created_at, responded_at "
            "FROM reminder_logs WHERE elder_id = %s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at ASC",
            (elder_id, start, end),
        )
        return [ReminderLog(*r) for r in rows]

    def mark_responded(self, elder_id: str, *, now: float, within_seconds: int) -> None:
        """把時間窗內最近一則提醒標為已回應；該則若已標記過則不動作。

        只標最近一則：長輩一句話不該同時「回應」早上與中午的兩則提醒。

        ⚠️ 「尚未標記」放在外層 UPDATE 的 WHERE（更新條件），**不可**放進子查詢
        （候選條件）：管線是每則長輩訊息呼叫一次，若候選條件濾掉已標記的，長輩每
        多講一句話就會往回啃一則更舊的提醒（串連標記），時間窗內所有提醒都會被標成
        已回應、回應率灌水到近 100%。改成先選最近一則、已標記就 no-op，第二句起自然
        不再往下啃，同時保留首次回應時間（不被後續發言覆寫）。
        """
        self._db.execute(
            "UPDATE reminder_logs SET responded_at = %s WHERE reminder_log_id = ("
            "SELECT reminder_log_id FROM reminder_logs "
            "WHERE elder_id = %s AND created_at >= %s AND created_at <= %s "
            "ORDER BY created_at DESC LIMIT 1) AND responded_at IS NULL",
            (now, elder_id, now - within_seconds, now),
        )


class FakeReminderLogStore:
    """ReminderLogStore 的記憶體替身（測試用，不碰 DB）。

    reminder_log_id 由索引虛構、僅供排序與標記；created_at 沿用注入的 clock，
    因回應時間窗的判定需要真實的時間語意（不能再用索引虛構）。
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._rows: list[ReminderLog] = []

    @property
    def recorded(self) -> list[tuple[str, str, str]]:
        """相容既有測試：只看 (elder_id, kind, content) 三元組。"""
        return [(r.elder_id, r.kind, r.content) for r in self._rows]

    def record(self, elder_id: str, kind: str, content: str) -> None:
        self._rows.append(
            ReminderLog(
                reminder_log_id=f"r{len(self._rows)}",
                elder_id=elder_id,
                kind=kind,
                content=content,
                created_at=self._clock().timestamp(),
                responded_at=None,
            )
        )

    def list_for_elder(self, elder_id: str) -> list[ReminderLog]:
        rows = [r for r in self._rows if r.elder_id == elder_id]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[ReminderLog]:
        rows = [r for r in self._rows if r.elder_id == elder_id and start <= r.created_at < end]
        return sorted(rows, key=lambda r: r.created_at)

    def mark_responded(self, elder_id: str, *, now: float, within_seconds: int) -> None:
        # 候選集不濾 responded_at（與 Pg 同一語意）：先選窗內最近一則，已標記就 no-op。
        # 若在此濾掉已標記的，連續發言會一路往回啃更舊的提醒（串連標記）。
        candidates = [
            (i, r)
            for i, r in enumerate(self._rows)
            if r.elder_id == elder_id and now - within_seconds <= r.created_at <= now
        ]
        if not candidates:
            return
        i, row = max(candidates, key=lambda pair: pair[1].created_at)
        if row.responded_at is None:
            self._rows[i] = replace(row, responded_at=now)


def safe_record(
    record: Callable[[str, str, str], None] | None, elder_id: str, kind: str, content: str
) -> None:
    if record is None:
        return
    try:
        record(elder_id, kind, content)
    except Exception:  # noqa: BLE001 - 記錄失敗不影響推播
        logger.warning("提醒紀錄落庫失敗 elder=%s kind=%s", elder_id, kind)
