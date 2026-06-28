"""記憶情境聚合：知識事實（不看查詢）＋情緒片段（依查詢語意檢索）。"""

from __future__ import annotations

from kinsun.episodic.recall import EpisodicRecaller
from kinsun.knowledge.recall import KnowledgeRecaller


class MemoryContext:
    def __init__(self, knowledge: KnowledgeRecaller, episodic: EpisodicRecaller) -> None:
        self._knowledge = knowledge
        self._episodic = episodic

    def recall(self, session_id: str, user_text: str) -> str:
        return self._knowledge.recall(session_id) + self._episodic.recall(session_id, user_text)
