"""Care Agent 樞紐：用系統指令呼叫 LLM 產生回覆。本切片僅最小職責。"""

from __future__ import annotations

from kinsun.llm import LLMClient

SYSTEM_PROMPT = (
    "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
    "一律用台灣繁體中文、口語、簡短地回應，語氣像晚輩關心長輩。"
    "你不是醫師，絕不提供醫療診斷或處方；遇到健康疑慮，溫柔建議對方告訴家人或就醫。"
)


class CareAgent:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def handle(self, user_text: str) -> str:
        return self._llm.generate(system_prompt=SYSTEM_PROMPT, user_text=user_text)
