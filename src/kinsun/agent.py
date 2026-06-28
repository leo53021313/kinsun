"""Care Agent 樞紐：載入今日記憶 → 呼叫 LLM → 寫回。"""

from __future__ import annotations

from kinsun.llm import LLMClient, Message
from kinsun.memory.store import MemoryStore

SYSTEM_PROMPT = (
    "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
    "一律用台灣繁體中文、口語、簡短地回應，語氣像晚輩關心長輩。"
    "你不是醫師，絕不提供醫療診斷或處方；遇到健康疑慮，溫柔建議對方告訴家人或就醫。"
)


class CareAgent:
    def __init__(self, llm: LLMClient, memory: MemoryStore) -> None:
        self._llm = llm
        self._memory = memory

    def handle(self, session_id: str, user_text: str) -> str:
        history = self._memory.recent(session_id)
        user_msg = Message("user", user_text)
        reply = self._llm.generate(system_prompt=SYSTEM_PROMPT, messages=[*history, user_msg])
        self._memory.append(session_id, user_msg)
        self._memory.append(session_id, Message("assistant", reply))
        return reply
