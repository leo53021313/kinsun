"""長期記憶骨幹批次：把今日對話寫入長期記憶（Mem0）。

CLI：PYTHONPATH=src uv run python -m kinsun.longterm.consolidation <session_id>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import load_settings
from kinsun.longterm import provenance
from kinsun.longterm.store import LongTermStore
from kinsun.memory.store import MemoryStore


def run_consolidation(session_id: str, *, short_term: MemoryStore, long_term: LongTermStore) -> int:
    turns = short_term.recent(session_id)
    if not turns:
        return 0
    long_term.add(session_id, turns, provenance=provenance.SELF_CLAIMED)
    return len(turns)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.longterm.consolidation <session_id>")
        return 1
    session_id = args[0]
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    from kinsun.longterm.store import Mem0LongTermStore
    from kinsun.mem0_factory import build_mem0_memory
    from kinsun.memory.store import PgMemoryStore

    short_term = PgMemoryStore(
        settings.database_url,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    long_term = Mem0LongTermStore(build_mem0_memory(settings), top_k=settings.longterm_top_k)
    written = run_consolidation(session_id, short_term=short_term, long_term=long_term)
    print(f"已整理：{written} 筆今日對話寫入長期記憶")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
