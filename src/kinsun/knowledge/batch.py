"""每日把短期對話抽成長期事實。

CLI：PYTHONPATH=src uv run python -m kinsun.knowledge.batch <session_id>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import load_settings
from kinsun.knowledge.extractor import FactExtractor
from kinsun.knowledge.store import FactStore, SqliteFactStore
from kinsun.llm import GeminiClient
from kinsun.memory.store import MemoryStore, SqliteMemoryStore


def run_fact_extraction(
    session_id: str,
    *,
    short_term: MemoryStore,
    extractor: FactExtractor,
    store: FactStore,
) -> int:
    facts = extractor.extract(session_id, short_term.recent(session_id))
    for fact in facts:
        store.add(fact)
    return len(facts)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.knowledge.batch <session_id>")
        return 1
    session_id = args[0]
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    short_term = SqliteMemoryStore(
        settings.memory_db_path,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    extractor = FactExtractor(
        GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.llm_timeout_seconds,
        )
    )
    store = SqliteFactStore(settings.knowledge_db_path)
    count = run_fact_extraction(session_id, short_term=short_term, extractor=extractor, store=store)
    print(f"已抽取 {count} 筆事實 → {settings.knowledge_db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
