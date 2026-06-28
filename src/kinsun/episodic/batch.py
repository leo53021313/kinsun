"""每日把短期對話抽成情緒片段並向量化入庫。

CLI：PYTHONPATH=src uv run python -m kinsun.episodic.batch <session_id>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from kinsun.config import load_settings
from kinsun.episodic.embeddings import Embedder, EmbeddingError, GeminiEmbedder
from kinsun.episodic.extractor import EpisodeExtractor
from kinsun.episodic.store import SqliteVectorStore, VectorStore
from kinsun.llm import GeminiClient
from kinsun.memory.store import MemoryStore, SqliteMemoryStore


def run_episode_extraction(
    session_id: str,
    *,
    short_term: MemoryStore,
    extractor: EpisodeExtractor,
    embedder: Embedder,
    store: VectorStore,
) -> int:
    episodes = extractor.extract(short_term.recent(session_id))
    stored = 0
    for episode in episodes:
        try:
            embedding = embedder.embed(episode)
        except EmbeddingError:
            continue
        store.add(session_id, episode, embedding)
        stored += 1
    return stored


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.episodic.batch <session_id>")
        return 1
    session_id = args[0]
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    short_term = SqliteMemoryStore(
        settings.memory_db_path,
        clock=lambda: datetime.now(tz),
        max_turns=settings.memory_max_turns,
    )
    extractor = EpisodeExtractor(
        GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.llm_timeout_seconds,
        )
    )
    embedder = GeminiEmbedder(api_key=settings.gemini_api_key, model=settings.embedding_model)
    store = SqliteVectorStore(settings.episodic_db_path)
    count = run_episode_extraction(
        session_id, short_term=short_term, extractor=extractor, embedder=embedder, store=store
    )
    print(f"已存入 {count} 段情緒記憶 → {settings.episodic_db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
