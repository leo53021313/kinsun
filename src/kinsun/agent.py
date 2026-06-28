"""Care Agent 樞紐：注入長期事實 + 載入今日記憶 → 呼叫 LLM → 寫回。"""

from __future__ import annotations

from kinsun.knowledge.recall import KnowledgeRecaller
from kinsun.llm import LLMClient, Message
from kinsun.memory.store import MemoryStore

SYSTEM_PROMPT = (
    "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
    "一律用台灣繁體中文、口語、簡短地回應，語氣像晚輩關心長輩。"
    "你不是醫師，絕不提供醫療診斷或用藥劑量建議；遇到健康疑慮，溫柔建議對方告訴家人或就醫。"
    "你是 AI，不要假裝是真人或家人；避免讓長者過度依賴你，適度鼓勵他與家人和現實生活互動。"
    "若長者陳述前後不一或可能記錯，不要爭辯，溫和回應即可。"
)


class CareAgent:
    def __init__(self, llm: LLMClient, memory: MemoryStore, recaller: KnowledgeRecaller) -> None:
        self._llm = llm
        self._memory = memory
        self._recaller = recaller

    def handle(self, session_id: str, user_text: str) -> str:
        system_prompt = SYSTEM_PROMPT + self._recaller.recall(session_id)
        history = self._memory.recent(session_id)
        user_msg = Message("user", user_text)
        reply = self._llm.generate(system_prompt=system_prompt, messages=[*history, user_msg])
        self._memory.append(session_id, user_msg)
        self._memory.append(session_id, Message("assistant", reply))
        return reply
