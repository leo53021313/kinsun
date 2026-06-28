"""情緒片段語意檢索。"""

from __future__ import annotations

from kinsun.episodic.embeddings import Embedder
from kinsun.episodic.store import VectorStore


class EpisodicRecaller:
    def __init__(self, embedder: Embedder, store: VectorStore, *, top_k: int = 3) -> None:
        self._embedder = embedder
        self._store = store
        self._top_k = top_k

    def recall(self, session_id: str, query: str) -> str:
        try:
            embedding = self._embedder.embed(query)
            episodes = self._store.search(session_id, embedding, self._top_k)
        except Exception:  # noqa: BLE001 - 記憶壞掉不可中斷對話
            return ""
        if not episodes:
            return ""
        return "\n你記得這位長者先前聊過：\n" + "\n".join(f"- {e}" for e in episodes)
