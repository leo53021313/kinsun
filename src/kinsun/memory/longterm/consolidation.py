"""長期記憶骨幹批次：把每個已結束完整日的對話寫入長期記憶（Mem0）。

於夜間（預設凌晨 3 點）執行，整理的是「今日之前、尚未整理過的每個完整日」：
- 正常每晚跑：只有昨天一個新完整日 → 整理昨天。
- worker 停機跨多日重啟（✅ 庚-06／A-18）：中間每個完整日逐日補齊，不漏天
  （唯一的永久資料遺失風險——短期記憶只留當天，過期即查不到）。
- 冪等（✅ 庚-13／A-19）：已整理過的日以 memory_consolidations 標記跳過，
  同日重跑（含 admin 手動觸發）不重覆寫入 mem0。

當下這天（today）不整理：只過幾小時、尚未結束，留待明晚。

CLI：PYTHONPATH=src uv run python -m kinsun.memory.longterm.consolidation <elder_id>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kinsun.config import load_settings
from kinsun.memory.longterm import provenance
from kinsun.memory.longterm.consolidation_log import ConsolidationLogStore
from kinsun.memory.longterm.store import LongTermStore
from kinsun.memory.shortterm import MemoryStore

_DAY_SECONDS = 86400.0  # 台灣無日光節約時間，一天固定 86400 秒。


def run_consolidation(
    elder_id: str,
    *,
    short_term: MemoryStore,
    long_term: LongTermStore,
    log: ConsolidationLogStore,
    now: datetime,
) -> int:
    """補整理 elder 今日之前尚未整理的每個完整日，回傳寫入 turn 總數。"""
    tz = now.tzinfo
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    already = log.consolidated_days(elder_id)
    # 只掃「上次整理之後」的區間：已整理日必在 today 之前，其最大值界定補整理起點。
    last = max(already) if already else None
    if last is None:
        since = 0.0
    else:
        last_start = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=tz)
        since = (last_start + timedelta(days=1)).timestamp()
    day_starts = short_term.day_starts_with_turns(
        elder_id, since=since, before=today_start.timestamp()
    )
    total = 0
    for day_start in day_starts:
        day = datetime.fromtimestamp(day_start, tz).strftime("%Y-%m-%d")
        if day in already:  # 防禦：since 已排除，這裡再擋一次確保冪等。
            continue
        turns = short_term.list_for_range(elder_id, start=day_start, end=day_start + _DAY_SECONDS)
        if turns:
            long_term.add(elder_id, turns, provenance=provenance.SELF_CLAIMED)
            total += len(turns)
        log.record(elder_id, day, turn_count=len(turns))
    return total


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.memory.longterm.consolidation <elder_id>")
        return 1
    elder_id = args[0]
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    from kinsun.db import Database
    from kinsun.memory.longterm.consolidation_log import PgConsolidationLogStore
    from kinsun.memory.longterm.mem0_factory import build_mem0_memory
    from kinsun.memory.longterm.store import Mem0LongTermStore
    from kinsun.memory.shortterm import PgMemoryStore

    db = Database.open(settings.database_url)
    try:
        short_term = PgMemoryStore(
            db,
            clock=lambda: datetime.now(tz),
            max_turns=settings.memory_max_turns,
        )
        long_term = Mem0LongTermStore(
            build_mem0_memory(settings),
            top_k=settings.longterm_top_k,
            health_top_k=settings.longterm_health_top_k,
        )
        log = PgConsolidationLogStore(db, clock=lambda: datetime.now(tz))
        written = run_consolidation(
            elder_id,
            short_term=short_term,
            long_term=long_term,
            log=log,
            now=datetime.now(tz),
        )
        print(f"已整理：{written} 筆對話寫入長期記憶")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
