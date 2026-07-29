"""短期記憶（今日對話上下文）：以 Postgres（Supabase）持久化每輪對話。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from kinsun.db import Database, _Errors
from kinsun.llm import Message


class MemoryStoreError(Exception):
    """短期記憶讀寫失敗。"""


def previous_day_bounds(now: datetime) -> tuple[float, float]:
    """回傳『剛結束的那一天』的 [起, 迄) Unix 時間戳（沿用 now 的時區）。

    供夜間整理批次使用：例如凌晨 3 點執行時，要整理前一天整天的對話，
    而不是當下這天才過幾小時的片段。
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_start = today_start - timedelta(days=1)
    return prev_start.timestamp(), today_start.timestamp()


def _first_per_day(timestamps: list[float], tz) -> list[float]:
    """把時刻依所在日期分組，每天只留最早的一筆（升序）。

    Pg 與 Fake 共用同一份分組邏輯，保證兩個 adapter 的日界切分語意一字不差。
    """
    first: dict[float, float] = {}
    for ts in sorted(timestamps):
        day = (
            datetime.fromtimestamp(ts, tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        if day not in first:
            first[day] = ts
    return [first[d] for d in sorted(first)]


class MemoryStore(Protocol):
    def append(self, elder_id: str, message: Message, *, at: datetime | None = None) -> None: ...
    def recent(self, elder_id: str) -> list[Message]: ...
    def previous_day(self, elder_id: str) -> list[Message]: ...
    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[Message]: ...
    def list_recent_in_range(
        self, elder_id: str, *, start: float, end: float, limit: int
    ) -> list[Message]: ...
    def day_starts_with_turns(
        self, elder_id: str, *, since: float, before: float
    ) -> list[float]: ...
    def first_user_turn_per_day(
        self, elder_id: str, *, since: float, before: float
    ) -> list[float]: ...
    def sessions(self) -> list[str]: ...
    def last_active(self, elder_id: str) -> float | None: ...


class PgMemoryStore:
    """短期記憶的 Postgres（Supabase）實作；介面同 MemoryStore。"""

    # 預設對齊 config 的 MEMORY_MAX_TURNS=200（✅ D-35 丙-5）；正式組裝一律由 settings 注入。
    def __init__(self, db: Database, clock: Callable[[], datetime], max_turns: int = 200) -> None:
        self._db = _Errors(db, lambda m: MemoryStoreError(f"記憶存取失敗：{m}"))
        self._clock = clock
        self._max_turns = max_turns

    def append(self, elder_id: str, message: Message, *, at: datetime | None = None) -> None:
        """`at`＝這一輪**長輩開口的時刻**；None 沿用寫入當下（原行為）。

        ⚠️ 為什麼需要它（spec 2026-07-28 P3）：`recent()` 依 `created_at DESC, id DESC`
        取回，而併發輪的寫入時刻是「誰先算完誰先寫」。長輩先問新聞（要查、慢）再問
        天氣（快），天氣會先寫進去——隔天 recall 讀到的對話順序是**顛倒的**，摘要也
        跟著錯。更糟的是兩輪的 user／assistant 訊息可能交錯寫入，讀起來像兩段被打散
        的對話。以開口時刻為排序鍵時，`created_at` 主導排序，同一輪的兩則自然相鄰，
        兩個問題一起消失。

        單輪路徑數值幾乎不變（開口時刻 ≈ 寫入時刻），故既有行為不受影響。
        """
        created_at = (at or self._clock()).timestamp()
        self._db.execute(
            "INSERT INTO turns (elder_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
            (elder_id, message.role, message.content, created_at),
        )

    def recent(self, elder_id: str) -> list[Message]:
        start = self._start_of_today()
        rows = self._db.query(
            "SELECT role, content FROM turns WHERE elder_id = %s AND created_at >= %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (elder_id, start, self._max_turns),
        )
        return [Message(role=r, content=t) for r, t in reversed(rows)]

    def previous_day(self, elder_id: str) -> list[Message]:
        """整理批次用：回傳『剛結束的那一天』整天的對話（時序由舊到新）。"""
        start, end = previous_day_bounds(self._clock())
        return self.list_for_range(elder_id, start=start, end=end)

    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[Message]:
        """回傳 [start, end) 區間的對話（時序由舊到新，上限 max_turns）——整理批次逐日補齊用。

        `LIMIT` 套在 `ASC` 上，超量時**留下的是最舊的**。這對逐日補齊（單日、幾乎不會
        碰到 max_turns）沒有影響，但**跨多天的窗不可用本方法**——會靜默截掉最近的幾天。
        跨多天請用 `list_recent_in_range`。
        """
        rows = self._db.query(
            "SELECT role, content FROM turns "
            "WHERE elder_id = %s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at ASC, id ASC LIMIT %s",
            (elder_id, start, end, self._max_turns),
        )
        return [Message(role=r, content=t) for r, t in rows]

    def list_recent_in_range(
        self, elder_id: str, *, start: float, end: float, limit: int
    ) -> list[Message]:
        """回傳 [start, end) 區間內**最近的 limit 輪**，仍以時序由舊到新排列。

        與 `list_for_range` 的差別只在超量時丟哪一端：本方法丟最舊的、保最新的。跨多天
        的讀取（每晚反思）必須用這個——長輩越健談，窗越容易滿，而「前天才糾正過的事」
        正是最不能被丟掉的資料。

        `limit` 由呼叫端傳入而非沿用 `max_turns`：聊天上下文（今日、MEMORY_MAX_TURNS）
        與反思（七天、REFLECTION_MAX_TURNS）是兩個不同的窗，共用一個上限就是病灶本身。

        取用 DESC 再反轉，讓 `LIMIT` 落在最新的那一端。
        """
        rows = self._db.query(
            "SELECT role, content FROM turns "
            "WHERE elder_id = %s AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (elder_id, start, end, limit),
        )
        return [Message(role=r, content=t) for r, t in reversed(rows)]

    def day_starts_with_turns(self, elder_id: str, *, since: float, before: float) -> list[float]:
        """回傳 [since, before) 內有對話的每個日界起點時間戳（配置時區、去重、升序）。

        供整理批次判斷「哪些完整日還沒整理」；日界依 clock 的時區切分（台灣無日光節約，
        一天固定 86400 秒）。
        """
        rows = self._db.query(
            "SELECT created_at FROM turns "
            "WHERE elder_id = %s AND created_at >= %s AND created_at < %s",
            (elder_id, since, before),
        )
        tz = self._clock().tzinfo
        starts = {
            datetime.fromtimestamp(ts, tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            for (ts,) in rows
        }
        return sorted(starts)

    def first_user_turn_per_day(self, elder_id: str, *, since: float, before: float) -> list[float]:
        """回傳 [since, before) 內每天第一則長輩發言的時刻（epoch 秒，升序、每天至多一筆）。

        自適應問候時間的唯一訊號（spec 2026-07-16）：她幾點起床，看她幾點開始講話。

        只取 `role='user'`：金孫自己的問候不算「她醒了」，否則訊號會被系統自己的排程
        時間污染——問候排在 08:00，讀回來的「起床時間」就永遠是 08:00。

        刻意不套 `max_turns`：這是統計量而非聊天上下文，截斷會讓多數日子的「第一則」
        消失、把中位數帶偏。日界依配置時區切分（台灣無日光節約，一天固定 86400 秒）；
        分組在 Python 端做，避免在 SQL 裡寫死時區轉換。
        """
        rows = self._db.query(
            "SELECT created_at FROM turns "
            "WHERE elder_id = %s AND role = 'user' AND created_at >= %s AND created_at < %s "
            "ORDER BY created_at ASC",
            (elder_id, since, before),
        )
        return _first_per_day([r[0] for r in rows], self._clock().tzinfo)

    def sessions(self) -> list[str]:
        rows = self._db.query(
            "SELECT DISTINCT elder_id FROM turns WHERE elder_id IS NOT NULL ORDER BY elder_id"
        )
        return [r[0] for r in rows]

    def last_active(self, elder_id: str) -> float | None:
        row = self._db.query_one(
            "SELECT MAX(created_at) FROM turns WHERE elder_id = %s AND role = 'user'",
            (elder_id,),
        )
        return row[0] if row and row[0] is not None else None

    def _start_of_today(self) -> float:
        now = self._clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.timestamp()


_FAKE_DEFAULT_NOW = datetime(2026, 6, 29, 3, 0, tzinfo=timezone(timedelta(hours=8)))


class FakeMemoryStore:
    """MemoryStore 的記憶體替身（測試用，不碰 DB）。

    忠實複製 Pg 的 max_turns 上限與時序（依 created_at、再依寫入序）：
    recent 回「今日最近 N 輪、由舊到新」，previous_day 回「前一天前 N 輪、由舊到新」。
    """

    def __init__(self, now: datetime | None = None, max_turns: int = 200) -> None:
        self._now = now or _FAKE_DEFAULT_NOW
        self._max_turns = max_turns
        self._turns: dict[str, list[tuple[float, Message]]] = {}

    def append(self, elder_id: str, message: Message, *, at: datetime | None = None) -> None:
        ts = (at or self._now).timestamp()
        self._turns.setdefault(elder_id, []).append((ts, message))

    def recent(self, elder_id: str) -> list[Message]:
        midnight = self._now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        rows = sorted(
            (
                (ts, i, m)
                for i, (ts, m) in enumerate(self._turns.get(elder_id, []))
                if ts >= midnight
            ),
            key=lambda r: (r[0], r[1]),
        )
        return [m for _, _, m in rows[-self._max_turns :]]

    def previous_day(self, elder_id: str) -> list[Message]:
        start, end = previous_day_bounds(self._now)
        return self.list_for_range(elder_id, start=start, end=end)

    def list_for_range(self, elder_id: str, *, start: float, end: float) -> list[Message]:
        # 忠實複製 Pg 的 ASC + LIMIT：超量時留下的是**最舊的**（見 Pg 端 docstring）。
        return [m for _, _, m in self._in_range(elder_id, start, end)[: self._max_turns]]

    def list_recent_in_range(
        self, elder_id: str, *, start: float, end: float, limit: int
    ) -> list[Message]:
        # 超量時留下的是**最新的** limit 輪，但仍由舊到新（對應 Pg 的 DESC + reversed）。
        if limit <= 0:
            return []  # 切片陷阱：limit=0 時 rows[-0:] 會回傳全部，Pg 的 LIMIT 0 則回空。
        return [m for _, _, m in self._in_range(elder_id, start, end)[-limit:]]

    def _in_range(
        self, elder_id: str, start: float, end: float
    ) -> list[tuple[float, int, Message]]:
        """區間內的對話，依（時間戳，寫入序）升序——對應 Pg 的 ORDER BY created_at, id。"""
        return sorted(
            (
                (ts, i, m)
                for i, (ts, m) in enumerate(self._turns.get(elder_id, []))
                if start <= ts < end
            ),
            key=lambda r: (r[0], r[1]),
        )

    def day_starts_with_turns(self, elder_id: str, *, since: float, before: float) -> list[float]:
        tz = self._now.tzinfo
        starts = {
            datetime.fromtimestamp(ts, tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            for ts, _ in self._turns.get(elder_id, [])
            if since <= ts < before
        }
        return sorted(starts)

    def first_user_turn_per_day(self, elder_id: str, *, since: float, before: float) -> list[float]:
        # 分組交給 _first_per_day，與 Pg 共用（見該函式與 Pg 端 docstring）。
        stamps = [
            ts
            for ts, m in self._turns.get(elder_id, [])
            if m.role == "user" and since <= ts < before
        ]
        return _first_per_day(stamps, self._now.tzinfo)

    def sessions(self) -> list[str]:
        return sorted(self._turns)

    def last_active(self, elder_id: str) -> float | None:
        users = [ts for ts, m in self._turns.get(elder_id, []) if m.role == "user"]
        return max(users) if users else None
