"""長期記憶骨幹批次：一次抽取 → 路由到知識庫與向量庫。

CLI：PYTHONPATH=src uv run python -m kinsun.longterm.consolidation <session_id>
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import load_settings
from kinsun.episodic.embeddings import Embedder, EmbeddingError, GeminiEmbedder
from kinsun.episodic.store import SqliteVectorStore, VectorStore
from kinsun.knowledge.store import FactStore, SqliteFactStore
from kinsun.llm import GeminiClient
from kinsun.longterm.extractor import ConsolidationExtractor
from kinsun.memory.store import MemoryStore, SqliteMemoryStore


@dataclass(frozen=True)
class ConsolidationResult:
    facts_stored: int
    episodes_stored: int


def run_consolidation(
    session_id: str,
    *,
    short_term: MemoryStore,
    extractor: ConsolidationExtractor,
    embedder: Embedder,
    fact_store: FactStore,
    vector_store: VectorStore,
) -> ConsolidationResult:
    consolidation = extractor.extract(session_id, short_term.recent(session_id))
    for fact in consolidation.facts:
        fact_store.add(fact)
    episodes_stored = 0
    for episode in consolidation.episodes:
        try:
            embedding = embedder.embed(episode)
        except EmbeddingError:
            continue
        vector_store.add(session_id, episode, embedding)
        episodes_stored += 1
    return ConsolidationResult(len(consolidation.facts), episodes_stored)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.longterm.consolidation <session_id>")
        return 1
    session_id = args[0]
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    short_term = SqliteMemoryStore(
        settings.memory_db_path,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    extractor = ConsolidationExtractor(
        GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.llm_timeout_seconds,
        )
    )
    embedder = GeminiEmbedder(api_key=settings.gemini_api_key, model=settings.embedding_model)
    fact_store = SqliteFactStore(settings.knowledge_db_path)
    vector_store = SqliteVectorStore(settings.episodic_db_path)
    result = run_consolidation(
        session_id,
        short_term=short_term,
        extractor=extractor,
        embedder=embedder,
        fact_store=fact_store,
        vector_store=vector_store,
    )
    print(f"已整理：{result.facts_stored} 筆事實、{result.episodes_stored} 段情緒記憶")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
